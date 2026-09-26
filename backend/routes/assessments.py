"""Standalone knife-skill assessment — the graded-assessment product.

The browser captures a wrist trajectory (MediaPipe) and POSTs it; we score it
SERVER-SIDE (authoritative — never trust a client score), persist it as an
Assessment (history + the demonstration-data flywheel), and return the official
grade. Deliberately SEPARATE from the cook-application gate (routes/skills.py),
which stamps CookProfile; this resource is user-scoped and gate-agnostic.

  POST /api/assessments        {metadata, trajectory[, video_url]} -> graded result
  GET  /api/assessments        -> the caller's assessment history (paginated)
  GET  /api/assessments/<id>   -> one assessment (owner only)
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g, abort

from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from services.skill_scoring import score_trajectory
from services.query_helpers import owned_or_404, paginate
from services.storage import upload_bytes, detect_video_kind
from models import Assessment
from services.assessment_media import owned_recording_path, InvalidRecording

assessments_bp = Blueprint("assessments", __name__)
log = logging.getLogger(__name__)

MAX_TRAJ_POINTS = 200_000
MAX_PAYLOAD_BYTES = 12 * 1024 * 1024     # trajectory JSON (incl. 3D hand landmarks)
MAX_VIDEO_BYTES = 80 * 1024 * 1024       # 80 MB clip
# Capture metadata we retain alongside the score (a fixed whitelist — never
# persist arbitrary client fields).
_META_KEYS = ("subject", "tier", "angle", "cut", "knife_hand",
              "duration_sec", "frames", "frames_with_hand", "schema")


def _own_namespace(video_url: str, uid: str) -> bool:
    """True only if the URL lives in THIS user's storage namespace — guards against
    a forged/foreign/other-user video_url being attached as the validation clip."""
    try:
        owned_recording_path(video_url, uid)
        return True
    except InvalidRecording:
        return False


def _resolve_video(body_video_url, multipart_file, uid):
    """Return a stored, OWN-namespace video URL (or None).

    The video is the validation artifact — every committed practice attempt should
    carry one (a human reviews it now; the video-CV engine validates it in Launch 2).
    Prefers a direct signed-URL upload (accepted only if it is in this user's
    namespace), and falls back to proxying a multipart file through the API when
    direct signing isn't configured.
    """
    if _own_namespace(body_video_url, uid):
        return body_video_url
    if body_video_url:
        log.warning("rejected non-own-namespace video_url for uid=%s", uid)
    if multipart_file is not None:
        data = multipart_file.read(MAX_VIDEO_BYTES + 1)
        if len(data) > MAX_VIDEO_BYTES:
            return None
        kind = detect_video_kind(data[:12])
        if kind is None:
            return None
        ts = int(datetime.now(timezone.utc).timestamp() * 1000)
        try:
            return upload_bytes(f"skill_videos/{uid}/{ts}.{kind}", data, f"video/{kind}")
        except Exception:
            log.warning("assessment video upload failed", exc_info=True)
    return None


# Which knife MOTION a requested cut needs (the B2B screen requests a guillotine_dice).
_CUT_TO_MOTION = {
    "guillotine_dice": "guillotine", "dice": "guillotine", "small_dice": "guillotine",
    "brunoise": "guillotine", "julienne": "guillotine", "batonnet": "guillotine",
    "mince": "rock_chop", "rock_chop": "rock_chop",
    "chiffonade": "slice", "rondelle": "slice", "slice": "slice",
}


def _technique_view(res):
    """Surface the detected knife TECHNIQUE (guillotine/rock_chop/slice) + whether it matches
    the cut the screen requested. The B2B-screen differentiator. Practice signal only (forgeable
    client trajectory, few-exemplar calibration) -- never a certifying verdict."""
    tech = res.get("technique") or {}
    det = tech.get("technique")
    if not det:
        return None
    requested = (res.get("metadata") or {}).get("cut")
    req_key = (requested or "").strip().lower().replace(" ", "_").replace("-", "_")
    req_motion = _CUT_TO_MOTION.get(req_key)
    return {
        "detected": det,
        "confidence": tech.get("confidence"),
        "lowCalibration": tech.get("low_calibration"),
        "requestedCut": requested,
        "matchesRequested": (det == req_motion) if (req_motion and det != "uncertain") else None,
        "note": "Provisional cut-type detection (forgeable practice signal, few-exemplar calibration); not a B2B verdict.",
    }


def _practice_view(res):
    """Reframe the raw oscillation result into an HONEST view: a demonstration-quality
    gate + chopping-rhythm PRACTICE feedback. NOT a skill grade — multi-angle testing
    proved wrist motion cannot rank knife skill (the score is dominated by camera
    angle: the same expert scored 85 front / 49 side). Real skill grading needs the
    cut-quality (piece-size/uniformity) engine on the video. So: detect a valid
    chopping DEMONSTRATION + give rhythm/consistency feedback; never claim a skill rank.
    """
    valid = bool(res.get("ok")) and bool(res.get("sufficient"))
    score = res.get("skill_score")
    feedback = None
    if valid and score is not None:
        feedback = {
            "rhythmConsistency": round(score),        # 0-100: how steady/even the chopping was
            "intervalCv": res.get("interval_cv"),
            "amplitudeCv": res.get("amplitude_cv"),
        }
    return {
        "demonstration": {
            "valid": valid,
            "chops": res.get("n_cycles"),
            "durationSec": res.get("bout_sec"),
            "reason": None if valid else (res.get("reason")
                      or "No steady chopping detected — chop a bit longer, then retake."),
        },
        "practiceFeedback": feedback,
        "technique": _technique_view(res),
        "note": ("Practice feedback on your chopping rhythm + consistency — NOT a knife-skill "
                 "grade. Your demonstration was saved."),
    }


def _assessment_response(a):
    """The honest API view of a stored Assessment (a captured chopping demonstration)."""
    res = a.result or {}
    out = {
        "id": str(a.id),
        "mode": res.get("mode", "practice"),
        "videoUrl": a.video_url,
        "createdAt": a.created_at.isoformat() if a.created_at else None,
    }
    out.update(_practice_view(res))
    return out


@assessments_bp.route("", methods=["POST"])
@assessments_bp.route("/", methods=["POST"])
@require_auth
@limiter.limit("20 per hour", key_func=lambda: g.user_id)
def create_assessment():
    """Score a captured trajectory and persist it (+ its video) as the caller's assessment.

    Accepts application/json {metadata, trajectory, video_url?} OR multipart/form-data
    with a 'payload' JSON field + an optional 'video' file. The video is stored either
    way — it is the artifact a human reviews now and the video-CV engine validates in
    Launch 2; a trajectory-only practice grade is never a validation verdict.
    """
    multipart_file = None
    if "multipart/form-data" in (request.content_type or ""):
        raw = request.form.get("payload")
        if not raw:
            return jsonify({"error": "missing 'payload' field"}), 400
        if len(raw) > MAX_PAYLOAD_BYTES:
            return jsonify({"error": "payload too large"}), 413
        try:
            body = json.loads(raw)
        except Exception:
            return jsonify({"error": "payload is not valid JSON"}), 400
        multipart_file = request.files.get("video")
    else:
        body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "JSON body or multipart payload required"}), 400
    traj = body.get("trajectory")
    meta = body.get("metadata") or {}
    if not isinstance(traj, list) or not isinstance(meta, dict):
        return jsonify({"error": "body needs {metadata, trajectory}"}), 400
    if len(traj) > MAX_TRAJ_POINTS:
        return jsonify({"error": "trajectory too large"}), 413

    # Authoritative server-side score (the client never decides the grade).
    result = score_trajectory(traj)

    # Store the video (the validation artifact): own-namespace signed URL, or a
    # multipart fallback upload. Never trust a foreign/other-user URL.
    video_url = _resolve_video(body.get("video_url") or None, multipart_file, g.user_id)
    stored = {
        **result,
        "mode": "practice",
        "metadata": {k: meta.get(k) for k in _META_KEYS},
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    with db_session() as session:
        a = Assessment(
            user_id=g.user_id,
            kind="technique",
            skill_score=result.get("skill_score"),
            verified=bool(result.get("verified")),
            tier=result.get("tier"),
            result=stored,
            video_url=video_url,
        )
        session.add(a)
        session.flush()
        # Prior completed assessments by this user (drives freemium gating).
        n_prior = (session.query(Assessment)
                   .filter(Assessment.user_id == g.user_id,
                           Assessment.id != a.id)
                   .count())
        out = _assessment_response(a)
    out["assessmentNumber"] = n_prior + 1
    out["isFirst"] = (n_prior == 0)
    out["hasVideo"] = bool(video_url)
    return jsonify(out), 201


@assessments_bp.route("", methods=["GET"])
@assessments_bp.route("/", methods=["GET"])
@require_auth
def list_assessments():
    """The caller's assessment history, newest first (paginated)."""
    with db_session() as session:
        q = (session.query(Assessment)
             .filter(Assessment.user_id == g.user_id)
             .order_by(Assessment.created_at.desc()))
        return jsonify(paginate(q, serialize=_assessment_response)), 200


@assessments_bp.route("/<assessment_id>", methods=["GET"])
@require_auth
def get_assessment(assessment_id):
    """One assessment, owner-scoped (404 — not 403 — if not theirs)."""
    try:
        aid = uuid.UUID(str(assessment_id))
    except (ValueError, AttributeError):
        abort(404)
    with db_session() as session:
        a = session.get(Assessment, aid)
        owned_or_404(a, "user_id", g.user_id)
        return jsonify(_assessment_response(a)), 200
