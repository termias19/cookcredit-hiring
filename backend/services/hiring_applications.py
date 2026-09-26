"""Hiring-application state projection from the append-only assessment history.

The browser never decides that an assessment is complete or which score is best. This
projection runs from stored sessions and server-finalized SkillAttempts, and can be called
from an HTTP read, the scoring worker, or a recovery job with the same result.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy.dialects.postgresql import insert

from models import (
    AssessmentShare, ATTEMPT_TERMINAL, HiringApplication, HiringApplicationEvent,
    HiringAssessmentSession, PipelineCard, RolePosting, SkillAttempt,
)
from services.partner_integrations import emit_partner_event
from services.partner_integrations import assessment_request_context
from services.assessment_outcomes import evaluate_assessment, normalize_criteria, allow_remaining_attempts
from services.live_motion_evidence import is_live_motion
from services.hiring_consent import ALL_ATTEMPTS_CONSENT_VERSIONS


def _utcnow():
    return datetime.now(timezone.utc)


def sync_application(session, application: HiringApplication, *, prefetched_sessions=None,
                     prefetched_attempts=None):
    """Project one application, optionally using batch-loaded rows for list endpoints."""
    sessions = (list(prefetched_sessions) if prefetched_sessions is not None else
                session.query(HiringAssessmentSession)
                .filter_by(application_id=application.id)
                .order_by(HiringAssessmentSession.started_at).all())
    def attempt_for(attempt_id):
        if prefetched_attempts is not None:
            return prefetched_attempts.get(attempt_id)
        return session.get(SkillAttempt, attempt_id)
    now = _utcnow()
    changed = False
    for item in sessions:
        if item.status == 'started' and item.expires_at <= now:
            item.status = 'expired'
            changed = True
        if item.status == 'processing' and item.attempt_id:
            attempt = attempt_for(item.attempt_id)
            if attempt and attempt.verification_state in ATTEMPT_TERMINAL:
                item.status = 'completed'
                item.completed_at = now
                changed = True

    completed = [item for item in sessions if item.status == 'completed' and item.attempt_id]
    attempts = [attempt_for(item.attempt_id) for item in completed]
    verified = [attempt for attempt in attempts if attempt
                and attempt.verification_state == 'VERIFIED'
                and not is_live_motion(attempt)
                and attempt.authoritative_score is not None]
    best = max(verified, key=lambda attempt: (float(attempt.authoritative_score), attempt.created_at)) if verified else None
    next_status = ('assessment_processing' if any(item.status == 'processing' for item in sessions)
                   else 'ready' if completed
                   else 'assessment_required')
    if application.status != 'withdrawn' and application.status != next_status:
        application.status = next_status
        changed = True

    # Consent covers the submitted attempts. Unclear evidence must remain
    # reviewable too; neither a passing score nor a fabricated credential is
    # required to let an employer watch it. A revoked grant is never reopened.
    # Older notices covered the selected result only. Do not silently broaden
    # an existing applicant's permission when this implementation is deployed.
    shared_attempts = attempts if application.consent_version in ALL_ATTEMPTS_CONSENT_VERSIONS else ([best] if best else [])
    for evidence in shared_attempts if application.status != 'withdrawn' else []:
        if evidence is None:
            continue
        meta = evidence.metadata_ or {}
        path, generation = meta.get('recording_path'), meta.get('recording_generation')
        if path and generation:
            session.execute(insert(AssessmentShare).values(
                id=uuid.uuid4(), role_posting_id=application.role_posting_id,
                attempt_id=evidence.id, applicant_id=application.applicant_id,
                storage_path=path, storage_generation=str(generation),
                consent_version=application.consent_version, granted_at=application.consented_at,
                revoked_at=None).on_conflict_do_nothing(constraint='uq_assessment_share'))
            card = (session.query(PipelineCard).filter_by(
                role_posting_id=application.role_posting_id,
                cook_id=application.applicant_id).one_or_none())
            if best and card and card.stage == 'assessing':
                card.stage = 'verified'

    if application.assessment_criteria is None:
        role = session.get(RolePosting, application.role_posting_id)
        from models import PartnerInvitation
        invitation = session.query(PartnerInvitation).filter_by(application_id=application.id).first()
        config = invitation.request_config if invitation else (role.requirements if role else {})
        config = config or {}
        application.assessment_criteria = normalize_criteria(config.get('assessmentCriteria'), skill_floor=config.get('skillFloor'))
    result_attempt = best or (attempt_for(completed[-1].attempt_id) if completed else None)
    result = None
    if application.status == 'ready':
        context = assessment_request_context(session, application.id)
        result = allow_remaining_attempts(evaluate_assessment(
            result_attempt, profile_version=context.get('assessmentProfileVersion') or 'knife-dice-v1',
            criteria=application.assessment_criteria), application.attempt_limit - len(completed))
    if application.screening_result != result:
        application.screening_result = result
        application.screening_outcome = result['outcome'] if result else None
        changed = True

    if changed:
        session.add(HiringApplicationEvent(
            application_id=application.id, actor_id=None,
            event_type='application_status', detail={'status': application.status}))
        if application.status == 'ready':
            role = session.get(RolePosting, application.role_posting_id)
            if role:
                context = assessment_request_context(session, application.id)
                result_attempt = best
                if result_attempt is None and completed:
                    result_attempt = attempt_for(completed[-1].attempt_id)
                outcome = application.screening_result
                event_data = {
                    **context,
                    'applicationId': str(application.id), 'roleId': str(role.id),
                    'status': application.status,
                    'assessmentStatus': (result_attempt.verification_state.lower()
                                         if result_attempt else 'no_gradeable_result'),
                    'score': (float(result_attempt.authoritative_score)
                              if result_attempt and result_attempt.authoritative_score is not None else None),
                    'result': outcome,
                }
                emit_partner_event(session, org_id=role.org_id,
                                   event_type='assessment.evidence_ready', data=event_data)
                emit_partner_event(session, org_id=role.org_id,
                                   event_type='assessment.completed', data=event_data)
    return sessions, best


def sync_application_for_attempt(session, attempt_id):
    """Project every hiring session linked to a newly terminal server attempt."""
    application_ids = [row[0] for row in (
        session.query(HiringAssessmentSession.application_id)
        .filter(HiringAssessmentSession.attempt_id == attempt_id).all())]
    for application_id in application_ids:
        application = session.get(HiringApplication, application_id)
        if application:
            sync_application(session, application)
