"""Beam: an eater broadcasts a craving to qualifying cooks; cooks respond with a note +
price; the eater reviews responders and picks ONE.

  POST /api/beams/photo            eater uploads an optional craving photo (validated, EXIF-stripped)
  POST /api/beams                  eater creates a beam; fans out to city-matched cooks; pushes them
  GET  /api/beams/mine             eater's own beams (+ responded count)
  GET  /api/beams/inbox            cook's open beams in their city (the recipient inbox)
  GET  /api/beams/<id>             beam detail (eater owner OR a matched cook); cook view marks seen
  GET  /api/beams/<id>/responses   eater owner: responder cards to choose from
  POST /api/beams/<id>/respond     cook: offer a note + price on a matched beam
  POST /api/beams/<id>/choose      eater owner: pick a responder -> beam 'fulfilled'
  POST /api/beams/<id>/cancel      eater owner: cancel an open beam
  POST /api/beams/<id>/decline     cook: dismiss a beam from their inbox

Choosing a cook connects the two parties (the client opens /cook/:id). The pick is settlement-light:
if the eater includes a `paymentMethod`, an Order row is created in the SAME transaction (cash-on-
delivery, or an online method that routes/orders.py later settles via Chapa); without one, choose
stays a pure connect. No payment PROVIDER is called here, so the broadcast flow never imports
settlement. Matching is city-wide first (lower(city) == cook_profiles.base_city); the eater_location
column is reserved for a later GPS radius.

Reuses: the image pipeline from routes/profile.py, storage.upload_bytes, the cooks.py input
sanitizers, owned_or_404 from query_helpers, and the FCM send path in services/notifications.py.
"""
import logging
import os
import uuid as _uuid
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, g, request, abort
from sqlalchemy import func

from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from services.storage import upload_bytes
from services.query_helpers import owned_or_404
from services.notifications import fcm_tokens_for, notify_beam_created, notify_beam_chosen
from routes.cooks import _clean_str, _num_or_none
from routes.profile import _detect_format, _strip_and_reencode, ALLOWED_FORMATS, MAX_FILE_SIZE
from models import User, CookProfile, Beam, BeamResponse, Order

beams_bp = Blueprint("beams", __name__)
log = logging.getLogger(__name__)

BEAM_TTL_HOURS = 24
MATCH_LIMIT = 200            # cap fan-out per beam (one beam_responses row per matched cook)

# Optional payment method an eater may attach when choosing a cook (creates an Order).
PAYMENT_METHODS = {"cod", "chapa", "telebirr", "cbe"}
# Order currency follows the deploy market (no payments-module import — keeps choose provider-free).
_ORDER_CURRENCY = "ETB" if os.environ.get("MARKET", "US").upper() == "ET" else "USD"


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_uuid(s):
    """Parse a URL path id into a UUID, or None if malformed (-> 404, never a 500)."""
    try:
        return _uuid.UUID(str(s))
    except (ValueError, TypeError, AttributeError):
        return None


def _require_active_cook(session, uid):
    """Return (user, cook_profile) only for an approved, skill-verified cook holding the
    'cook' role; otherwise abort 403. Mirrors the public-discovery gate in cooks.py and the
    role rules in auth.py (_grant_cook_if_approved)."""
    user = session.get(User, uid)
    cp = user.cook_profile if user else None
    if (user is None or cp is None or not cp.approved or not cp.skill_verified
            or "cook" not in (user.roles or [])):
        abort(403)
    return user, cp


def _valid_craving_photo(url, uid):
    """Accept a photo URL only if it is a Firebase download URL inside THIS eater's own
    cravings/ namespace (defends against pointing a beam at someone else's/arbitrary object)."""
    if not isinstance(url, str):
        return None
    if not url.startswith("https://firebasestorage.googleapis.com/"):
        return None
    if f"cravings%2F{uid}%2F" not in url:
        return None
    return url[:1000]


def _expire_stale(session):
    """Lazily flip open beams whose TTL has passed to 'expired'. Idempotent and
    multi-instance-safe; called atop the inbox/mine reads (a cron job can take over later)."""
    session.query(Beam).filter(
        Beam.status == "open", Beam.expires_at <= _utcnow()
    ).update({"status": "expired"}, synchronize_session=False)


def _cook_card(user, cp, resp):
    """Responder card for the eater's choose screen (reuses the public cook fields)."""
    return {
        "responseId": str(resp.id),
        "status": resp.status,
        "note": resp.note,
        "price": float(resp.price) if resp.price is not None else None,
        "cookId": user.id,
        "name": user.name,
        "photoUrl": user.photo_url,
        "skillTier": cp.skill_tier if cp else None,
        "skillScore": float(cp.skill_score) if (cp and cp.skill_score is not None) else None,
        "baseCity": cp.base_city if cp else None,
        "baseState": cp.base_state if cp else None,
        "cuisines": (cp.cuisines or []) if cp else [],
    }


# ── Craving photo upload (optional) ─────────────────────────────────────────────
@beams_bp.route("/photo", methods=["POST"])
@require_auth
@limiter.limit("20 per hour", key_func=lambda: g.user_id)
def upload_craving_photo():
    """Validate + EXIF-strip a craving photo and store it under cravings/{uid}/. Returns {url}.
    Same hardened pipeline as portfolio uploads (magic-byte sniff + Pillow re-encode)."""
    content_length = request.content_length
    if content_length is not None and content_length > MAX_FILE_SIZE + 8192:
        return jsonify({"error": "File too large. Maximum size is 10 MB."}), 413
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided. Send as multipart/form-data field 'file'."}), 400
    data = file.read(MAX_FILE_SIZE + 1)
    if len(data) > MAX_FILE_SIZE:
        return jsonify({"error": "File too large. Maximum size is 10 MB."}), 413

    img_format = _detect_format(data[:12])
    if img_format is None:
        return jsonify({"error": "File type not allowed. Upload a JPEG, PNG, or WebP photo "
                                 "(HEIC is not supported)."}), 415
    try:
        clean = _strip_and_reencode(data, img_format)
    except Exception:
        return jsonify({"error": "Image could not be processed. The file may be corrupt."}), 415

    ext = "jpg" if img_format == "JPEG" else img_format.lower()
    ts = int(_utcnow().timestamp() * 1000)
    path = f"cravings/{g.user_id}/craving_{ts}.{ext}"
    try:
        url = upload_bytes(path, clean, ALLOWED_FORMATS[img_format])
    except Exception:
        log.exception("craving photo upload failed")
        return jsonify({"error": "Storage upload failed. Please try again."}), 500
    return jsonify({"url": url}), 201


# ── Create a beam (eater) ───────────────────────────────────────────────────────
@beams_bp.route("", methods=["POST"])
@beams_bp.route("/", methods=["POST"])
@require_auth
@limiter.limit("10 per hour", key_func=lambda: g.user_id)
def create_beam():
    """Broadcast a craving to approved, skill-verified cooks in the eater's city. Fans out a
    'pending' recipient row per matched cook and pushes them (best-effort, after commit)."""
    data = request.get_json(silent=True) or {}
    craving = _clean_str(data.get("cravingText"), 500)
    if not craving:
        return jsonify({"error": "Tell cooks what you are craving."}), 400

    scope = data.get("scope")
    scope = scope if scope in ("nearby", "citywide") else "citywide"

    tokens, beam = [], None
    with db_session() as session:
        user = session.get(User, g.user_id)
        ep = user.eater_profile if user else None
        city = _clean_str(data.get("city"), 120) or (ep.address_city if ep else None)
        if not city:
            return jsonify({"error": "Add your city so cooks can find your beam."}), 400
        state = _clean_str(data.get("state"), 60) or (ep.address_state if ep else None)
        photo = _valid_craving_photo(data.get("photoUrl"), g.user_id)

        beam = Beam(
            eater_id=g.user_id,
            craving_text=craving,
            photo_url=photo,
            scope=scope,
            city=city,
            state=state,
            status="open",
            expires_at=_utcnow() + timedelta(hours=BEAM_TTL_HOURS),
        )
        session.add(beam)
        session.flush()  # assign beam.id before inserting recipient rows

        cook_rows = (session.query(User.id)
                     .join(CookProfile, CookProfile.user_id == User.id)
                     .filter(CookProfile.approved.is_(True),
                             CookProfile.skill_verified.is_(True),
                             func.lower(CookProfile.base_city) == city.lower(),
                             User.id != g.user_id)
                     .limit(MATCH_LIMIT)
                     .all())
        cook_ids = [r[0] for r in cook_rows]
        for cid in cook_ids:
            session.add(BeamResponse(beam_id=beam.id, cook_id=cid, status="pending"))
        beam.matched_count = len(cook_ids)

        tokens = fcm_tokens_for(session, cook_ids)  # gather inside the session, send after commit

    notify_beam_created(tokens, beam)
    return jsonify({"beam": beam.to_dict(), "matchedCount": beam.matched_count}), 201


# ── Eater: my beams ─────────────────────────────────────────────────────────────
@beams_bp.route("/mine", methods=["GET"])
@require_auth
def my_beams():
    """The signed-in eater's beams, newest first, each with a responded count."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("perPage", 20))))
    except (TypeError, ValueError):
        page, per_page = 1, 20

    with db_session() as session:
        _expire_stale(session)
        q = (session.query(Beam)
             .filter(Beam.eater_id == g.user_id)
             .order_by(Beam.created_at.desc()))
        rows = q.offset((page - 1) * per_page).limit(per_page + 1).all()
        more = len(rows) > per_page
        items = []
        for b in rows[:per_page]:
            d = b.to_dict()
            d["responseCount"] = sum(1 for r in b.responses if r.status in ("responded", "chosen"))
            items.append(d)
        return jsonify({"beams": items, "page": page, "hasMore": more}), 200


# ── Cook: inbox of open beams in my city ────────────────────────────────────────
@beams_bp.route("/inbox", methods=["GET"])
@require_auth
def cook_inbox():
    """Open, unexpired beams matched to the signed-in cook that they have not yet acted on
    (their recipient row is still 'pending'). Newest first."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("perPage", 20))))
    except (TypeError, ValueError):
        page, per_page = 1, 20

    with db_session() as session:
        _require_active_cook(session, g.user_id)
        _expire_stale(session)
        q = (session.query(Beam, BeamResponse)
             .join(BeamResponse, BeamResponse.beam_id == Beam.id)
             .filter(BeamResponse.cook_id == g.user_id,
                     BeamResponse.status == "pending",
                     Beam.status == "open",
                     Beam.expires_at > _utcnow())
             .order_by(Beam.created_at.desc()))
        rows = q.offset((page - 1) * per_page).limit(per_page + 1).all()
        more = len(rows) > per_page
        items = []
        for beam, resp in rows[:per_page]:
            d = beam.to_dict()
            d["responseId"] = str(resp.id)
            items.append(d)
        return jsonify({"beams": items, "page": page, "hasMore": more}), 200


# ── Beam detail (eater owner OR matched cook) ───────────────────────────────────
@beams_bp.route("/<beam_id>", methods=["GET"])
@require_auth
def get_beam(beam_id):
    bid = _parse_uuid(beam_id)
    if bid is None:
        abort(404)
    with db_session() as session:
        beam = session.get(Beam, bid)
        if beam is None:
            abort(404)
        if beam.eater_id == g.user_id:
            d = beam.to_dict()
            d["responseCount"] = sum(1 for r in beam.responses if r.status in ("responded", "chosen"))
            return jsonify(d), 200
        # Otherwise the viewer must be a matched cook.
        my = (session.query(BeamResponse)
              .filter(BeamResponse.beam_id == beam.id, BeamResponse.cook_id == g.user_id)
              .first())
        if my is None:
            abort(404)
        if my.seen_at is None:
            my.seen_at = _utcnow()
        d = beam.to_dict()
        d["myResponse"] = my.to_dict()
        return jsonify(d), 200


# ── Eater owner: responders to choose from ──────────────────────────────────────
@beams_bp.route("/<beam_id>/responses", methods=["GET"])
@require_auth
def beam_responses(beam_id):
    bid = _parse_uuid(beam_id)
    if bid is None:
        abort(404)
    with db_session() as session:
        beam = owned_or_404(session.get(Beam, bid), "eater_id", g.user_id)
        rows = (session.query(BeamResponse, User, CookProfile)
                .join(User, User.id == BeamResponse.cook_id)
                .outerjoin(CookProfile, CookProfile.user_id == User.id)
                .filter(BeamResponse.beam_id == beam.id,
                        BeamResponse.status.in_(("responded", "chosen", "not_chosen")))
                .order_by(BeamResponse.responded_at.asc().nullslast())
                .all())
        cards = [_cook_card(user, cp, resp) for (resp, user, cp) in rows]
        return jsonify({"beam": beam.to_dict(), "responses": cards}), 200


# ── Cook: respond to a beam ─────────────────────────────────────────────────────
@beams_bp.route("/<beam_id>/respond", methods=["POST"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def respond_to_beam(beam_id):
    bid = _parse_uuid(beam_id)
    if bid is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        _require_active_cook(session, g.user_id)
        beam = session.get(Beam, bid)
        if beam is None:
            abort(404)
        my = (session.query(BeamResponse)
              .filter(BeamResponse.beam_id == beam.id, BeamResponse.cook_id == g.user_id)
              .first())
        if my is None:
            abort(404)  # not a matched recipient
        if beam.status != "open" or beam.expires_at <= _utcnow():
            return jsonify({"error": "This beam is no longer open."}), 409
        my.note = _clean_str(data.get("note"), 500)
        my.price = _num_or_none(data.get("price"), 0, 999999)
        my.status = "responded"
        my.responded_at = _utcnow()
        if my.seen_at is None:
            my.seen_at = _utcnow()
        return jsonify({"response": my.to_dict()}), 200


# ── Eater owner: choose a responder ─────────────────────────────────────────────
@beams_bp.route("/<beam_id>/choose", methods=["POST"])
@require_auth
@limiter.limit("30 per hour", key_func=lambda: g.user_id)
def choose_responder(beam_id):
    bid = _parse_uuid(beam_id)
    if bid is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    rid = _parse_uuid(data.get("responseId"))
    if rid is None:
        return jsonify({"error": "Pick a responder."}), 400
    method = (data.get("paymentMethod") or "").strip().lower()
    if method and method not in PAYMENT_METHODS:
        return jsonify({"error": "Unknown payment method."}), 400

    tokens, beam, card, order_dict = [], None, None, None
    with db_session() as session:
        beam = owned_or_404(session.get(Beam, bid), "eater_id", g.user_id)
        if beam.status != "open":
            return jsonify({"error": "This beam is already closed."}), 409
        chosen = session.get(BeamResponse, rid)
        if chosen is None or chosen.beam_id != beam.id or chosen.status != "responded":
            return jsonify({"error": "That responder is no longer available."}), 400

        # Losers among the responders go to not_chosen; the picked one to chosen.
        (session.query(BeamResponse)
         .filter(BeamResponse.beam_id == beam.id,
                 BeamResponse.status == "responded",
                 BeamResponse.id != chosen.id)
         .update({"status": "not_chosen"}, synchronize_session=False))
        chosen.status = "chosen"
        beam.status = "fulfilled"
        beam.chosen_cook_id = chosen.cook_id
        beam.chosen_response_id = chosen.id

        # Optional settlement record (no provider call here — orders.py drives any online payment).
        if method:
            order = Order(
                beam_id=beam.id,
                beam_response_id=chosen.id,
                eater_id=g.user_id,
                cook_id=chosen.cook_id,
                amount=chosen.price,
                currency=_ORDER_CURRENCY,
                payment_method=method,
                payment_status="cod_pending" if method == "cod" else "pending",
            )
            session.add(order)
            session.flush()            # assign order.id before the session closes
            order_dict = order.to_dict()

        cook = session.get(User, chosen.cook_id)
        cp = cook.cook_profile if cook else None
        card = _cook_card(cook, cp, chosen) if cook else None
        tokens = fcm_tokens_for(session, [chosen.cook_id])

    notify_beam_chosen(tokens, beam)
    return jsonify({"beam": beam.to_dict(), "chosenCook": card, "order": order_dict}), 200


# ── Eater owner: cancel an open beam ────────────────────────────────────────────
@beams_bp.route("/<beam_id>/cancel", methods=["POST"])
@require_auth
@limiter.limit("30 per hour", key_func=lambda: g.user_id)
def cancel_beam(beam_id):
    bid = _parse_uuid(beam_id)
    if bid is None:
        abort(404)
    with db_session() as session:
        beam = owned_or_404(session.get(Beam, bid), "eater_id", g.user_id)
        if beam.status != "open":
            return jsonify({"error": "Only an open beam can be cancelled."}), 409
        beam.status = "cancelled"
        return jsonify({"beam": beam.to_dict()}), 200


# ── Cook: dismiss a beam from the inbox ─────────────────────────────────────────
@beams_bp.route("/<beam_id>/decline", methods=["POST"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def decline_beam(beam_id):
    bid = _parse_uuid(beam_id)
    if bid is None:
        abort(404)
    with db_session() as session:
        _require_active_cook(session, g.user_id)
        my = (session.query(BeamResponse)
              .filter(BeamResponse.beam_id == bid, BeamResponse.cook_id == g.user_id)
              .first())
        if my is None:
            abort(404)
        if my.status in ("pending", "responded"):
            my.status = "declined"
        return jsonify({"ok": True}), 200
