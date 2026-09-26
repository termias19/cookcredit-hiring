"""Public cook profiles + the cook self-view (dashboard).

  GET /api/cooks/<id>  PUBLIC (no auth) — the eater-facing cook profile. Returns ONLY
                       publicly-visible cooks (approved AND skill_verified). The biometric
                       clip is never included (CookProfile.to_dict omits skill_test_video_url),
                       and email is never exposed.
  GET /api/cooks/me    cook self-view for the dashboard (auth required); works even while the
                       application is still pending/unverified.

Rating/reviews and bookings/earnings are intentionally DEFERRED (no marketplace tables are
served yet) — returned as null/0 so the UI shows a calm "new cook" state instead of fake data.
"""
import logging

from flask import Blueprint, jsonify, g, request
from sqlalchemy import func, cast
from geoalchemy2 import Geography

from extensions import limiter
from middleware.auth import require_auth, require_verified_email
from services.location import coordinates, read_search_token, LocationUnavailable
from services.database import db_session
from models import User, CookProfile  # noqa: F401  (CookProfile used via relationship)

cooks_bp = Blueprint("cooks", __name__)
log = logging.getLogger(__name__)


@cooks_bp.route('/nearby', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('120 per hour;30 per minute', key_func=lambda: g.user_id)
def nearby_cooks():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='Invalid search'), 400
    try:
        lat, lng = read_search_token(body.get('locationToken'), g.user_id)
        radius = body.get('radiusMiles', 25)
        if isinstance(radius, bool) or radius not in (5, 10, 25, 50, 100):
            raise ValueError('Invalid radius')
        page = body.get('page', 1)
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 1000:
            raise ValueError('Invalid page')
    except ValueError:
        return jsonify(error='Choose a valid search area and radius', code='invalid_location'), 400
    except LocationUnavailable:
        return jsonify(error='Location search is unavailable', code='location_unavailable'), 503
    point = cast(func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326), Geography)
    distance = func.ST_Distance(CookProfile.base_location, point)
    with db_session() as session:
        rows = (session.query(User, CookProfile, distance.label('meters'))
            .join(CookProfile, CookProfile.user_id == User.id)
            .filter(CookProfile.approved.is_(True), CookProfile.skill_verified.is_(True),
                    CookProfile.base_location.isnot(None),
                    func.ST_DWithin(CookProfile.base_location, point, radius * 1609.344))
            .order_by(distance, User.id).offset((page - 1) * 24).limit(25).all())
        data = [{
            'id': user.id, 'name': user.name, 'photoUrl': user.photo_url,
            'baseCity': cook.base_city, 'baseState': cook.base_state,
            'cuisines': cook.cuisines or [],
            'skillScore': float(cook.skill_score) if cook.skill_score is not None else None,
            'pricePerHour': float(cook.price_per_hour) if cook.price_per_hour is not None else None,
            'distanceMiles': round(meters / 1609.344), 'distanceIsApproximate': True,
        } for user, cook, meters in rows[:24]]
    response = jsonify(cooks=data, page=page, hasMore=len(rows) > 24, radiusMiles=radius)
    response.headers['Cache-Control'] = 'no-store'
    return response


@cooks_bp.route('/me/service-area', methods=['PUT', 'DELETE'])
@require_auth
@require_verified_email
@limiter.limit('20 per hour', key_func=lambda: g.user_id)
def service_area():
    body = request.get_json(silent=True) if request.method == 'PUT' else None
    if request.method == 'PUT':
        try:
            if not isinstance(body, dict) or body.get('accepted') is not True:
                raise ValueError('Consent required')
            lat, lng = coordinates(body.get('lat'), body.get('lng'))
        except ValueError:
            return jsonify(error='A valid location and explicit consent are required'), 400
    with db_session() as session:
        cook = session.get(CookProfile, g.user_id)
        if cook is None:
            return jsonify(error='Cook profile not found'), 404
        # Device coordinates are supplied by the owner, not a Google cached result.
        # Round before persistence: this is a service area, never a published home pin.
        cook.base_location = (f'SRID=4326;POINT({round(lng, 2)} {round(lat, 2)})'
                              if request.method == 'PUT' else None)
    return jsonify(saved=True, configured=request.method == 'PUT', precision='approximate')


# ── Input sanitizers for the self-edit PATCH (defensive: bound every client value) ───────────────
def _clean_str(v, maxlen):
    """A trimmed string capped at maxlen, or None if blank / not a string."""
    if not isinstance(v, str):
        return None
    s = v.strip()[:maxlen]
    return s or None


def _str_list(v, cap=20, item_len=40):
    """A de-duplicated list of trimmed strings (blanks dropped), capped in count + element length."""
    if not isinstance(v, list):
        return []
    out, seen = [], set()
    for x in v:
        s = x.strip()[:item_len] if isinstance(x, str) else ""
        k = s.lower()
        if s and k not in seen:
            seen.add(k)
            out.append(s)
        if len(out) >= cap:
            break
    return out


def _num_or_none(v, lo, hi):
    """A float clamped to [lo, hi] (2dp), or None if missing / NaN / unparseable."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n:           # NaN
        return None
    return round(max(lo, min(hi, n)), 2)


def _int_or_none(v, lo, hi):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, n))


def _public_cook(user: User, cp: CookProfile) -> dict:
    """Biometric-safe public payload: identity (name/photo, NO email) + the cook profile
    fields (to_dict already omits the video URL) + dishes. Deferred fields are explicit."""
    public_fields = {'userId', 'bio', 'specialties', 'cuisines', 'pricePerHour',
        'travelRadiusMiles', 'baseCity', 'baseState', 'portfolioPhotos',
        'skillScore', 'skillVerified', 'skillTier', 'skillTestAt',
        'yearsExperience', 'dietaryCapabilities'}
    d = {key: value for key, value in cp.to_dict().items() if key in public_fields}
    d.update({
        "id": user.id,
        "name": user.name,
        "photoUrl": user.photo_url,
        "dishes": [dish.to_dict() for dish in (user.dishes or [])],
        # Deferred (no source yet) — UI should render a "new cook" state, not fake stars.
        "rating": None,
        "reviewCount": 0,
    })
    return d


@cooks_bp.route("", methods=["GET"])
@cooks_bp.route("/", methods=["GET"])
@limiter.limit("120 per hour")
def list_cooks():
    """Public, paginated list of discoverable cooks (approved AND skill_verified),
    newest-verified first. Lightweight cards (no dishes/video). Optional ?city= / ?cuisine=
    filters and ?page=/&perPage=."""
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("perPage", 24))))
    except ValueError:
        page, per_page = 1, 24
    city = (request.args.get("city") or "").strip().lower()
    cuisine = (request.args.get("cuisine") or "").strip().lower()

    with db_session() as session:
        q = (session.query(User, CookProfile)
             .join(CookProfile, CookProfile.user_id == User.id)
             .filter(CookProfile.approved.is_(True), CookProfile.skill_verified.is_(True)))
        if city:
            q = q.filter(func.lower(CookProfile.base_city) == city)
        q = q.order_by(CookProfile.skill_test_at.desc().nullslast())
        rows = q.offset((page - 1) * per_page).limit(per_page + 1).all()

        more = len(rows) > per_page
        cooks = []
        for user, cp in rows[:per_page]:
            cuisines = cp.cuisines or []
            if cuisine and cuisine not in [c.lower() for c in cuisines]:
                continue
            cooks.append({
                "id": user.id,
                "name": user.name,
                "photoUrl": user.photo_url,
                "skillScore": float(cp.skill_score) if cp.skill_score is not None else None,
                "skillTier": cp.skill_tier,
                "baseCity": cp.base_city,
                "baseState": cp.base_state,
                "cuisines": cuisines,
                "specialties": cp.specialties or [],
                "pricePerHour": float(cp.price_per_hour) if cp.price_per_hour is not None else None,
            })
        return jsonify({"cooks": cooks, "page": page, "hasMore": more}), 200


@cooks_bp.route("/<cook_id>", methods=["GET"])
@limiter.limit("120 per hour")
def get_cook(cook_id):
    """Public cook profile. 404 unless the cook is publicly visible (approved + skill_verified)."""
    with db_session() as session:
        user = session.get(User, cook_id)
        if user is None:
            return jsonify({"error": "not found"}), 404
        cp = user.cook_profile
        if cp is None or not cp.approved or not cp.skill_verified:
            return jsonify({"error": "not found"}), 404
        return jsonify(_public_cook(user, cp)), 200


@cooks_bp.route("/me", methods=["GET"])
@require_auth
def get_cook_me():
    """The signed-in cook's own profile for the dashboard. Includes owner-only fields
    (application status, Stripe-connect) and works while still pending/unverified."""
    with db_session() as session:
        user = session.get(User, g.user_id)
        if user is None or user.cook_profile is None:
            return jsonify({"error": "no cook profile"}), 404
        cp = user.cook_profile
        d = _public_cook(user, cp)
        cpd = cp.to_dict()
        d.update({
            "applicationStatus": cpd.get("applicationStatus"),
            "approved": cp.approved,
            "stripeConnected": bool(cp.stripe_account_id),
        })
        return jsonify(d), 200


@cooks_bp.route("/me", methods=["PATCH"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def update_cook_me():
    """Self-service edit of the signed-in cook's descriptive profile (Qwick/Indeed-style: editable
    anytime, whether the application is pending or approved). PATCH semantics — only the keys present
    in the body are changed. The EARNED skill credential (skill_score/skill_verified/skill_tier from
    the camera test), Stripe-connect, approval/admin state, and email are NEVER writable here."""
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        user = session.get(User, g.user_id)
        if user is None or user.cook_profile is None:
            return jsonify({"error": "no cook profile"}), 404
        cp = user.cook_profile

        if "bio" in data:
            cp.bio = _clean_str(data.get("bio"), 2000)
        if "cuisines" in data:
            cp.cuisines = _str_list(data.get("cuisines"))
        if "specialties" in data:
            cp.specialties = _str_list(data.get("specialties"))
        if "dietaryCapabilities" in data:
            cp.dietary_capabilities = _str_list(data.get("dietaryCapabilities"))
        if "baseCity" in data:
            cp.base_city = _clean_str(data.get("baseCity"), 120)
        if "baseState" in data:
            cp.base_state = _clean_str(data.get("baseState"), 60)
        if "pricePerHour" in data:                                   # Numeric(6,2) -> max 9999.99
            cp.price_per_hour = _num_or_none(data.get("pricePerHour"), 0, 9999)
        if "travelRadiusMiles" in data:                             # Numeric(4,1) -> max 999.9
            cp.travel_radius_miles = _num_or_none(data.get("travelRadiusMiles"), 0, 500)
        if "yearsExperience" in data:
            cp.years_experience = _int_or_none(data.get("yearsExperience"), 0, 80)

        # Return the same shape as GET /api/cooks/me so the client can refresh state in place.
        d = _public_cook(user, cp)
        cpd = cp.to_dict()
        d.update({
            "applicationStatus": cpd.get("applicationStatus"),
            "approved": cp.approved,
            "stripeConnected": bool(cp.stripe_account_id),
        })
        return jsonify(d), 200
