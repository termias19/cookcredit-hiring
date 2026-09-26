"""Applicant-controlled sharing of one existing attempt for one hiring role."""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g
from sqlalchemy.dialects.postgresql import insert
from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from services.assessment_media import inspect_recording, InvalidRecording
from models import AssessmentShare, SkillAttempt, RolePosting, Org

sharing_bp = Blueprint('assessment_sharing', __name__)
CONSENT_VERSION = 'cookcredit-employer-evidence-v1'
CONSENT_TEXT = ('Share this assessment recording and its results with this company for this role. '
                'You can revoke future access. Playback links already issued expire within five minutes.')


def as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


@sharing_bp.route('/<role_id>/<attempt_id>', methods=['GET', 'POST'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def share_assessment(role_id, attempt_id):
    rid, aid = as_uuid(role_id), as_uuid(attempt_id)
    if not rid or not aid:
        return jsonify(error='Not found'), 404
    with db_session() as session:
        attempt = session.get(SkillAttempt, aid)
        role = session.get(RolePosting, rid)
        if not attempt or attempt.user_id != g.user_id or not role:
            return jsonify(error='Not found'), 404
        org = session.get(Org, role.org_id)
        if not org:
            return jsonify(error='Not found'), 404
        if request.method == 'GET':
            grant = session.query(AssessmentShare).filter_by(role_posting_id=rid, attempt_id=aid,
                                                             applicant_id=g.user_id).one_or_none()
            return jsonify(company=org.name, role=role.title, attemptId=str(aid),
                           consentVersion=CONSENT_VERSION, consentText=CONSENT_TEXT,
                           shareId=str(grant.id) if grant else None,
                           shareStatus=('revoked' if grant.revoked_at else 'shared') if grant else 'not-shared',
                           ready=attempt.verification_state == 'VERIFIED')
        if role.status != 'open':
            return jsonify(error='This role is closed'), 409
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or body.get('accepted') is not True or body.get('consentVersion') != CONSENT_VERSION:
            return jsonify(error='Explicit acceptance of the current sharing notice is required'), 400
        if attempt.verification_state != 'VERIFIED' or not attempt.video_url:
            return jsonify(error='This assessment is not ready to share'), 409
        try:
            path, generation, _ = inspect_recording(attempt.video_url, g.user_id)
        except InvalidRecording:
            return jsonify(error='This recording cannot be shared'), 409
        except Exception:
            return jsonify(error='Recording storage is unavailable; try again'), 503
        # The URL can refer to an overwritten legacy object. Sharing must bind the
        # generation that was actually scored, not just the current object name.
        scored = (attempt.metadata_ or {}).get('recording_generation')
        if not scored or str(scored) != generation:
            return jsonify(error='This recording needs generation-bound verification before sharing'), 409
        values = dict(id=uuid.uuid4(), role_posting_id=rid, attempt_id=aid,
                      applicant_id=g.user_id, storage_path=path, storage_generation=generation,
                      consent_version=CONSENT_VERSION, granted_at=datetime.now(timezone.utc), revoked_at=None)
        # Revoked grants cannot be silently reinstated by a delayed POST. A new
        # attempt is required for a new grant in this initial security slice.
        session.execute(insert(AssessmentShare).values(**values).on_conflict_do_nothing(
            constraint='uq_assessment_share'))
        grant = session.query(AssessmentShare).filter_by(role_posting_id=rid, attempt_id=aid).one()
        if grant.revoked_at:
            return jsonify(error='This sharing grant was revoked'), 409
        return jsonify(shareId=str(grant.id), status='shared'), 200


@sharing_bp.route('/<share_id>/revoke', methods=['POST'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def revoke_share(share_id):
    sid = as_uuid(share_id)
    if not sid:
        return jsonify(error='Not found'), 404
    with db_session() as session:
        grant = session.query(AssessmentShare).filter_by(id=sid, applicant_id=g.user_id).with_for_update().one_or_none()
        if not grant:
            return jsonify(error='Not found'), 404
        if grant.revoked_at is None:
            grant.revoked_at = datetime.now(timezone.utc)
    return jsonify(status='revoked', existingPlaybackExpiresWithinSeconds=300)
