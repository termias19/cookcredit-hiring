"""Cook chopping skill-test gate — the dual-score path.

The browser scores the capture ON-DEVICE (MediaPipe + eliteStroke) for an instant
PROVISIONAL number, then uploads the clip. We:
  1. record the on-device (claimed) score + a cheap server recompute of the trajectory,
  2. create a PROVISIONAL SkillAttempt (idempotent on the client session_id),
  3. enqueue a recompute that re-derives the score from the VIDEO via the GPU scorer and
     reconciles it against the claim (motion = tamper-check, dice = skill verdict),
  4. advance the attempt to VERIFIED | DISPUTED | INSUFFICIENT.
A credential is stamped on the CookProfile ONLY on VERIFIED.

  POST /api/skills/upload-url  -> signed PUT URL for a DIRECT browser->Storage upload
  POST /api/skills/submit      multipart: payload(JSON {metadata,trajectory,session_id,on_device[,video_url]}) + optional video
  GET  /api/skills/<id>        -> one attempt (both scores + verification state); owner only
  POST /api/skills/recompute   internal (Cloud Tasks): body {attempt_id}; X-Internal-Secret gated
  GET  /api/skills/me          -> current verified skill status for the logged-in cook
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g

from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from services.storage import signed_upload_url, upload_bytes
from services.assessment_media import owned_recording_path, inspect_recording, InvalidRecording
from services.skill_scoring import score_trajectory
from services.skill_attempts import create_or_get_attempt, run_recompute, transition
from services.scoring_dispatch import drain_scoring_dispatch
from services.internal_auth import internal_request_authorized
from models import CookProfile, SkillAttempt

skills_bp = Blueprint("skills", __name__)
log = logging.getLogger(__name__)

MAX_VIDEO_BYTES = 80 * 1024 * 1024     # 80 MB
MAX_TRAJ_POINTS = 200_000
MAX_PAYLOAD_BYTES = 12 * 1024 * 1024   # trajectory JSON (incl. 3D hand landmarks)
_VIDEO_TYPES = {"video/webm": "webm", "video/mp4": "mp4"}

# Cuts the GPU scorer has a baked-in profile for (serving/profiles/*.json).
KNOWN_PROFILES = {"guillotine_dice", "rock_chop_mince"}
CUT_TO_PROFILE = {
    "dice": "guillotine_dice", "small_dice": "guillotine_dice", "guillotine_dice": "guillotine_dice",
    "brunoise": "guillotine_dice", "julienne": "guillotine_dice", "batonnet": "guillotine_dice",
    "mince": "rock_chop_mince", "rock_chop_mince": "rock_chop_mince", "rock_chop": "rock_chop_mince",
}


def _resolve_profile(cut) -> str:
    """Map a requested cut to a GPU profile_id; default to guillotine_dice."""
    if not cut:
        return "guillotine_dice"
    c = str(cut).strip().lower()
    if c in KNOWN_PROFILES:
        return c
    return CUT_TO_PROFILE.get(c, "guillotine_dice")


def _num(x):
    """A real finite number, else None (never trust client JSON types)."""
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


_SESSION_NAME_RE = None


def _safe_session_name(sid) -> str | None:
    """A session id usable as a storage object name: 8-64 chars of [A-Za-z0-9_-]
    only (no dots/slashes — nothing that can traverse or fake an extension)."""
    global _SESSION_NAME_RE
    if _SESSION_NAME_RE is None:
        import re
        _SESSION_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
    s = str(sid or "").strip()
    return s if _SESSION_NAME_RE.match(s) else None


def _detect_video(header: bytes) -> str | None:
    """webm/mp4 from magic bytes (never trust Content-Type)."""
    if header[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if header[4:8] == b"ftyp":
        return "mp4"
    return None


@skills_bp.route("/upload-url", methods=["POST"])
@require_auth
@limiter.limit("20 per hour", key_func=lambda: g.user_id)
def skill_upload_url():
    """Mint a signed PUT URL so the browser uploads the clip DIRECTLY to Storage
    (keeps the 80 MB video off the API workers). Body: {content_type}. The client
    PUTs the file to upload_url, then passes video_url to /submit."""
    body = request.get_json(silent=True) or {}
    ct = body.get("content_type", "video/webm")
    ext = _VIDEO_TYPES.get(ct)
    if ext is None:
        return jsonify({"error": "content_type must be video/webm or video/mp4"}), 415
    # Name the object by the client's capture session when given (strictly sanitized),
    # so a retry of the SAME capture overwrites one object instead of orphaning
    # duplicates (an interrupted submit used to leave two identical 27 MB blobs).
    # Falls back to a timestamp name when no session id is supplied.
    sid = _safe_session_name(body.get("session_id"))
    name = sid or str(int(datetime.now(timezone.utc).timestamp() * 1000))
    path = f"skill_videos/{g.user_id}/{name}.{ext}"
    try:
        info = signed_upload_url(path, ct)
    except Exception:
        log.warning("signed_upload_url failed", exc_info=True)  # detail to server logs only
        return jsonify({"error": "signed upload unavailable"}), 503
    return jsonify({"upload_url": info["upload_url"], "video_url": info["download_url"],
                    "content_type": ct}), 200


@skills_bp.route("/submit", methods=["POST"])
@require_auth
@limiter.limit("10 per hour", key_func=lambda: g.user_id)
def submit_skill_test():
    """Record the on-device score + create a PROVISIONAL attempt, then enqueue the
    authoritative video recompute. Returns {attempt_id, verificationState, ...} for the
    two-phase UI to poll. Idempotent on the client session_id."""
    # ---- parse payload (metadata + trajectory + session + on-device claim) ----
    raw = request.form.get("payload")
    if not raw:
        return jsonify({"error": "missing 'payload' field (JSON)"}), 400
    if len(raw) > MAX_PAYLOAD_BYTES:
        return jsonify({"error": "payload too large"}), 413
    try:
        payload = json.loads(raw)
    except Exception:
        return jsonify({"error": "payload is not valid JSON"}), 400
    if not isinstance(payload, dict):
        return jsonify(error='payload must be a JSON object'), 400
    traj = payload.get("trajectory")
    meta = payload.get("metadata") or {}
    if not isinstance(traj, list) or not isinstance(meta, dict):
        return jsonify({"error": "payload needs {metadata, trajectory}"}), 400
    if len(traj) > MAX_TRAJ_POINTS:
        return jsonify({"error": "trajectory too large"}), 413

    session_id = str(payload.get("session_id") or "").strip() or str(uuid.uuid4())
    on_device = payload.get("on_device") if isinstance(payload.get("on_device"), dict) else {}
    on_device_score = _num(on_device.get("score"))
    profile_id = _resolve_profile(meta.get("cut"))

    # ---- cheap server recompute of the trajectory (provisional/local; still forgeable) ----
    local_result = score_trajectory(traj)

    # ---- resolve the clip: signed-URL path (preferred) or multipart fallback ----
    video_url = payload.get("video_url") or None
    if video_url:
        try:
            owned_recording_path(video_url, g.user_id)
        except InvalidRecording:
            return jsonify(error='Recording must belong to the signed-in applicant'), 400
    file = request.files.get("video")
    if video_url is None and file is not None:
        data = file.read(MAX_VIDEO_BYTES + 1)
        if len(data) > MAX_VIDEO_BYTES:
            return jsonify({"error": "video too large (max 80 MB)"}), 413
        kind = _detect_video(data[:12])
        if kind is None:
            return jsonify({"error": "not a webm/mp4 video"}), 415
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        try:
            video_url = upload_bytes(f"skill_videos/{g.user_id}/{ts}.{kind}", data, f"video/{kind}")
        except Exception:
            log.warning("video upload failed", exc_info=True)
            return jsonify(error='Recording upload failed; retry submission'), 503

    stored_meta = {k: meta.get(k) for k in
                   ("subject", "tier", "angle", "cut", "knife_hand",
                    "duration_sec", "frames", "frames_with_hand", "schema")}
    if video_url:
        try:
            path, generation, _ = inspect_recording(video_url, g.user_id)
        except InvalidRecording:
            return jsonify(error='Recording size or format is not supported'), 400
        except Exception:
            return jsonify(error='Recording upload could not be verified; retry submission'), 503
        stored_meta.update(recording_path=path, recording_generation=generation)

    # ---- idempotent create + decide what to enqueue ----
    with db_session() as session:
        attempt, created = create_or_get_attempt(
            session, user_id=g.user_id, session_id=session_id, profile_id=profile_id,
            on_device_score=on_device_score, on_device_block=on_device,
            local_result=local_result, trajectory=traj, metadata=stored_meta, video_url=video_url)
        session.flush()
        attempt_id = str(attempt.id)
        state = attempt.verification_state
        has_video = bool(attempt.video_url)
        # No video on a fresh attempt -> can't verify; honest terminal (practice only).
        if created and not has_video:
            transition(session, attempt, "INSUFFICIENT",
                       {"reason": "no video uploaded — provisional practice score only"})
            state = attempt.verification_state
        view = attempt.to_dict()

    # The same transaction persisted dispatch_due_at. The scheduler can deliver
    # it even if this process stops before returning the response.
    status = 201 if created else 200
    return jsonify({"attempt_id": attempt_id, **view}), status


@skills_bp.route("/recompute", methods=["POST"])
@limiter.exempt
def internal_recompute():
    """Internal endpoint hit by Cloud Tasks to run the authoritative recompute. Gated by
    a shared secret (and OIDC at the infra layer). NOT user-authenticated."""
    if not internal_request_authorized(request):
        return jsonify({"error": "forbidden"}), 403
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error='Expected a JSON object'), 400
    attempt_id = body.get("attempt_id")
    try:
        attempt_id = str(uuid.UUID(str(attempt_id)))
    except ValueError:
        return jsonify({"error": "A valid attempt_id is required"}), 400
    try:
        result = run_recompute(attempt_id)
    except Exception:
        log.exception("recompute endpoint failed for %s", attempt_id)
        return jsonify({"error": "recompute failed"}), 500
    if result is None:
        return jsonify(error='Recompute is incomplete; retry delivery'), 503
    return jsonify({"ok": True}), 200


@skills_bp.route('/dispatch-pending', methods=['POST'])
@limiter.exempt
def internal_dispatch_pending():
    """Scheduler entry point. Provision its recurring trigger before accepting traffic."""
    if not internal_request_authorized(request):
        return jsonify(error='forbidden'), 403
    stats = drain_scoring_dispatch()
    # Return non-success for queue failures so monitoring/scheduler sees outages.
    return jsonify(stats), 503 if stats['failed'] else 200


@skills_bp.route("/<attempt_id>", methods=["GET"])
@require_auth
def get_skill_attempt(attempt_id):
    """One attempt: both scores + the verification state. Owner-scoped (404 otherwise)."""
    try:
        aid = uuid.UUID(str(attempt_id))
    except ValueError:
        return jsonify({"error": "not found"}), 404
    with db_session() as session:
        attempt = session.get(SkillAttempt, aid)
        if attempt is None or attempt.user_id != g.user_id:
            return jsonify({"error": "not found"}), 404
        return jsonify(attempt.to_dict()), 200


@skills_bp.route("/me", methods=["GET"])
@require_auth
def my_skill_status():
    """Current VERIFIED skill status for the logged-in cook (stamped from the latest
    VERIFIED attempt)."""
    with db_session() as session:
        # The most recent attempt's verdict + reason, so the client can EXPLAIN an
        # unverified state (a DISPUTED user used to see only "not verified" with no
        # why once they left the test page).
        last = (session.query(SkillAttempt)
                .filter(SkillAttempt.user_id == g.user_id)
                .order_by(SkillAttempt.created_at.desc())
                .first())
        last_attempt = None
        if last is not None:
            recon = last.reconciliation if isinstance(last.reconciliation, dict) else {}
            last_attempt = {
                "state": last.verification_state,
                "reason": recon.get("reason") or recon.get("summary"),
                "at": last.created_at.isoformat() if last.created_at else None,
            }

        cp = session.get(CookProfile, g.user_id)
        if cp is None:
            return jsonify({"skill_score": None, "verified": False, "tier": None,
                            "tested": False, "last_attempt": last_attempt}), 200
        return jsonify({
            "skill_score": float(cp.skill_score) if cp.skill_score is not None else None,
            "verified": bool(cp.skill_verified),
            "tier": cp.skill_tier,
            "tested": cp.skill_test_at is not None,
            "tested_at": cp.skill_test_at.isoformat() if cp.skill_test_at else None,
            "result": cp.skill_test_result,
            "last_attempt": last_attempt,
        }), 200
