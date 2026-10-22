"""Hosted hiring application and unchanged CookCredit Skill handoff."""
import os
import re
import hashlib
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy import and_, func, or_

from flask import Blueprint, jsonify, request, g, Response
from services import hiring_cv, hiring_reviews
from services.hiring_consent import APPLICATION_CONSENT_VERSION
from extensions import limiter
from middleware.auth import require_auth, require_verified_email
from middleware.app_check import require_app_check
from services import landmark_recording
from services import engine_recording_import
from services.hiring_presentation import session_presentation
from services.database import db_session
from services.assessment_outcomes import normalize_criteria
from services.live_motion_evidence import hiring_motion_criteria, VERSION, PROFILE_ID
from services.engine_assessment import verified_engine_assessment, InvalidEngineAssessment
from services.hiring_capture import validate_capture, bind_capture
from services.skill_attempts import create_or_get_attempt
from services.hiring_applications import sync_application as _sync_application
from models import (
    User, CookProfile, Org, RolePosting, PipelineCard, SkillAttempt,
    HiringApplication, HiringAssessmentSession, HiringApplicationEvent,
    AssessmentShare, ATTEMPT_TERMINAL, PartnerInvitation,
)
from routes.business import _can, _role_owned, _assessment_report, _org_for
from services.partner_integrations import assessment_request_context, emit_partner_event

hiring_bp = Blueprint('hiring', __name__)

APPLICATION_CONSENT_TEXT = (
    'Share my name, CV if supplied, answers, approximate location, and each submitted assessment attempt, including '
    'its recording, measurements and review status, with the named company for this role. '
    'Browser measurements are provisional; a person must make the hiring decision. I may revoke '
    'future recording access; already issued playback links expire within five minutes. '
    'Hiring copies of recordings, landmarks and CVs are retained for up to 30 days.'
)
ANSWER_TEXT_LIMIT = 2000
SESSION_TTL = timedelta(hours=2)
APPLICATION_STATUSES = {'assessment_required', 'assessment_processing', 'ready', 'withdrawn'}


def _utcnow():
    return datetime.now(timezone.utc)


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _page_cursor(application):
    payload = json.dumps({
        'submittedAt': application.submitted_at.isoformat(), 'id': str(application.id),
    }, separators=(',', ':')).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip('=')


def _decode_page_cursor(value):
    if not value:
        return None
    try:
        raw = str(value)
        payload = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        submitted_at = datetime.fromisoformat(payload['submittedAt'])
        if submitted_at.tzinfo is None:
            submitted_at = submitted_at.replace(tzinfo=timezone.utc)
        return submitted_at, uuid.UUID(payload['id'])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ValueError('Invalid pagination cursor')


def _public_role(role, org, invitation=None):
    data = role.to_dict()
    if invitation:
        config = invitation.request_config or {}
        data.update(title=invitation.job_title or data['title'],
                    applicationQuestions=config.get('applicationQuestions') or [],
                    locationLabel=config.get('locationLabel'), attemptLimit=invitation.attempt_limit)
    config = (invitation.request_config or {}) if invitation else (role.requirements or {})
    raw_criteria = config.get('assessmentCriteria')
    skill_floor = (role.requirements or {}).get('skillFloor')
    criteria = (hiring_motion_criteria(raw_criteria) if not raw_criteria and skill_floor is None
                else normalize_criteria(raw_criteria, skill_floor=skill_floor))
    return {
        'id': data['id'], 'title': data['title'], 'status': data['status'],
        'company': {'name': org.name, 'city': org.city,
                    'logoUrl': org.brand_logo_url,
                    'brandColor': org.brand_color or '#1F6F5C'},
        'location': {'label': data.get('locationLabel'), 'point': data.get('loc'),
                     'workMode': data.get('workMode'), 'radiusM': data.get('radiusM')},
        'employment': {'type': data.get('employmentType'), 'shifts': data.get('shifts'),
                       'payMin': data.get('payMin'), 'payMax': data.get('payMax'),
                       'tips': data.get('tips')},
        'description': data.get('description'),
        'questions': data.get('applicationQuestions') or [],
        'attemptLimit': data.get('attemptLimit') or 3,
        'environment': role.integration_environment,
        'assessment': {
            'name': 'CookCredit Knife Skill assessment',
            'experience': 'The existing CookCredit Skill capture opens in its own secure page.',
            'automaticHiringDecision': False,
            'criteria': criteria,
        },
        'cvRequired': not bool(invitation or role.integration_managed),
        'consentVersion': APPLICATION_CONSENT_VERSION,
        'consentText': APPLICATION_CONSENT_TEXT,
    }


def _clean_location(value):
    if not isinstance(value, dict):
        return None
    city = re.sub(r'\s+', ' ', str(value.get('city') or '').strip())[:120]
    out = {'city': city or None}
    if value.get('lat') is not None or value.get('lng') is not None:
        try:
            lat, lng = float(value.get('lat')), float(value.get('lng'))
        except (TypeError, ValueError):
            raise ValueError('Location coordinates are invalid')
        if not -90 <= lat <= 90 or not -180 <= lng <= 180:
            raise ValueError('Location coordinates are invalid')
        # Roughly 100 m precision: useful for distance filtering without an exact home point.
        out.update(lat=round(lat, 3), lng=round(lng, 3))
    return out if any(v is not None for v in out.values()) else None


def _answers(schema, supplied):
    if not isinstance(supplied, dict):
        raise ValueError('Answers must be an object')
    clean = {}
    for question in schema:
        qid, kind = question['id'], question['type']
        value = supplied.get(qid)
        empty = value is None or value == '' or value == []
        if empty:
            if question.get('required'):
                raise ValueError(f"Required answer missing: {question['label']}")
            continue
        if kind == 'yes_no':
            if not isinstance(value, bool):
                raise ValueError(f"Invalid answer: {question['label']}")
            clean[qid] = value
        elif kind in ('select', 'multiselect'):
            values = value if isinstance(value, list) else [value]
            allowed = set(question.get('options') or [])
            if not values or len(values) > len(allowed) or any(v not in allowed for v in values):
                raise ValueError(f"Invalid answer: {question['label']}")
            clean[qid] = values if kind == 'multiselect' else values[0]
        else:
            text = re.sub(r'\s+', ' ', str(value).strip())[:ANSWER_TEXT_LIMIT]
            if kind == 'phone' and not re.fullmatch(r'[+0-9() .-]{7,40}', text):
                raise ValueError(f"Invalid phone number: {question['label']}")
            clean[qid] = text
    return clean


def _application_view(application, sessions):
    terminal = [s for s in sessions if s.status == 'completed']
    return {
        'id': str(application.id), 'roleId': str(application.role_posting_id),
        'status': application.status, 'answers': application.answers or {},
        'applicantName': (application.applicant_details or {}).get('name'),
        'hasCv': hiring_cv.available((application.applicant_details or {}).get('cv'), application.submitted_at) and application.status != 'withdrawn',
        'questions': application.question_schema or [], 'location': application.location,
        'assessmentCriteria': application.assessment_criteria,
        'screeningResult': application.screening_result if application.status != 'withdrawn' else None,
        'attemptLimit': application.attempt_limit, 'attemptsCompleted': len(terminal),
        'attemptsRemaining': max(0, application.attempt_limit - len(terminal)),
        'attempts': [
            {'sessionId': str(s.id), 'slot': s.slot, 'status': s.status,
             'attemptId': str(s.attempt_id) if s.attempt_id else None,
             'completedAt': s.completed_at.isoformat() if s.completed_at else None}
            for s in sorted(sessions, key=lambda item: (item.slot, item.started_at))
        ],
        'submittedAt': application.submitted_at.isoformat() if application.submitted_at else None,
    }


def _latest_assessment(session, sessions):
    completed = [item for item in sessions if item.status == 'completed' and item.attempt_id]
    if not completed:
        return None
    attempt = session.get(SkillAttempt, completed[-1].attempt_id)
    return _assessment_report(attempt) if attempt else None


def _ensure_cook_profile(session, user_id):
    if session.get(CookProfile, user_id) is None:
        session.add(CookProfile(user_id=user_id))


@hiring_bp.route('/roles/<role_id>', methods=['GET'])
def public_role(role_id):
    rid = _uuid(role_id)
    if not rid:
        return jsonify(error='Not found'), 404
    with db_session() as session:
        role = session.get(RolePosting, rid)
        org = session.get(Org, role.org_id) if role else None
        if not role or not org or role.status != 'open':
            return jsonify(error='Not found'), 404
        raw_invitation = str(request.args.get('invite') or '').strip()
        invitation = None
        if raw_invitation:
            invitation = session.query(PartnerInvitation).filter_by(
                token_hash=hashlib.sha256(raw_invitation.encode()).hexdigest(),
                role_posting_id=role.id).one_or_none()
            if (not invitation or invitation.status not in ('pending', 'accepted')
                    or (invitation.status == 'pending' and invitation.expires_at <= _utcnow())):
                return jsonify(error='This invitation is invalid or expired'), 409
        if role.integration_managed and not invitation:
            return jsonify(error='A valid assessment invitation is required'), 404
        response = jsonify(role=_public_role(role, org, invitation))
        response.headers['Cache-Control'] = 'no-store'
        return response, 200


@hiring_bp.route('/roles/<role_id>/apply', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('20 per hour', key_func=lambda: g.user_id)
def apply(role_id):
    rid = _uuid(role_id)
    try:
        body = json.loads(request.form.get('application', '{}')) if request.mimetype == 'multipart/form-data' else request.get_json(silent=True) or {}
    except (ValueError, TypeError):
        return jsonify(error='Invalid application'), 400
    if not rid or not isinstance(body, dict):
        return jsonify(error='Invalid application'), 400
    if (body.get('acceptedEvidenceShare') is not True
            or body.get('consentVersion') != APPLICATION_CONSENT_VERSION):
        return jsonify(error='Explicit acceptance of the current application notice is required'), 400
    with db_session() as session:
        role = session.get(RolePosting, rid)
        if not role or role.status != 'open':
            return jsonify(error='This role is not accepting applications'), 409
        org = session.get(Org, role.org_id)
        invitation = None
        raw_invitation = str(body.get('invitationToken') or '').strip()
        if role.integration_managed and not raw_invitation:
            return jsonify(error='A valid assessment invitation is required'), 409
        if raw_invitation:
            if not g.email_verified:
                return jsonify(error='Verify your email before accepting this invitation',
                               code='email_unverified'), 403
            invitation = (session.query(PartnerInvitation).filter_by(
                token_hash=hashlib.sha256(raw_invitation.encode()).hexdigest(),
                role_posting_id=role.id).with_for_update().one_or_none())
            if (not invitation or invitation.status not in ('pending', 'accepted')
                    or (invitation.status == 'pending' and invitation.expires_at <= _utcnow())):
                return jsonify(error='This invitation is invalid or expired'), 409
            if invitation.candidate_email.casefold() != str(g.email or '').casefold():
                return jsonify(error='Sign in with the email address that received this invitation'), 403
            if invitation.status == 'accepted':
                prior = session.get(HiringApplication, invitation.application_id) if invitation.application_id else None
                if not prior or prior.applicant_id != g.user_id:
                    return jsonify(error='This invitation has already been used'), 409
        # Serialize application creation per applicant, including two different
        # invitations for the same role. Do not attach a new request to old evidence.
        applicant = session.query(User).filter_by(id=g.user_id).with_for_update().one()
        application = (session.query(HiringApplication).filter_by(
            role_posting_id=rid, applicant_id=g.user_id).with_for_update().one_or_none())
        if application and invitation and invitation.application_id != application.id:
            return jsonify(error='An application already exists for this job. Continue the original invitation.',
                           code='application_already_exists'), 409
        config = (invitation.request_config or {}) if invitation else (role.requirements or {})
        schema = list(application.question_schema if application else config.get('applicationQuestions') or [])
        try:
            answers = _answers(schema, body.get('answers') or {})
            location = _clean_location(body.get('location'))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        if config.get('locationLabel') and not (location or {}).get('city'):
            return jsonify(error='City or area is required for this location-based role'), 400
        if application and application.status not in ('assessment_required',):
            sessions, _ = _sync_application(session, application)
            return jsonify(application=_application_view(application, sessions), company=org.name), 200
        if application is None:
            try:
                applicant_name = hiring_cv.full_name(body.get('fullName', applicant.name))
                cv_data = hiring_cv.read_cv(request.files.get('cv')) if not (invitation or role.integration_managed) else None
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
            try:
                criteria = hiring_motion_criteria(config.get('assessmentCriteria'), skill_floor=config.get('skillFloor'))
            except ValueError as exc:
                return jsonify(error=str(exc), code='assessment_contract_review_required'), 409
            application = HiringApplication(
                id=uuid.uuid4(), role_posting_id=rid, applicant_id=g.user_id, status='assessment_required',
                applicant_details={'name': applicant_name},
                question_schema=schema, answers=answers, location=location,
                assessment_criteria=criteria,
                attempt_limit=(invitation.attempt_limit if invitation
                               else max(1, min(3, int(config.get('attemptLimit') or 3)))),
                consent_version=APPLICATION_CONSENT_VERSION, consented_at=_utcnow())
            if cv_data is not None:
                try:
                    application.applicant_details = {'name': applicant_name, 'cv': hiring_cv.store_cv(application.id, cv_data)}
                    hiring_cv.cleanup_on_rollback(session, application.applicant_details['cv'])
                except Exception:
                    return jsonify(error='CV upload did not finish. Please try again.'), 503
            session.add(application)
            _ensure_cook_profile(session, g.user_id)
            session.flush()
            if invitation and invitation.status != 'accepted':
                invitation.status = 'accepted'
                invitation.application_id = application.id
                invitation.accepted_at = _utcnow()
            session.add(PipelineCard(role_posting_id=rid, cook_id=g.user_id, stage='assessing'))
            session.add(HiringApplicationEvent(application_id=application.id, actor_id=g.user_id,
                                               event_type='application_submitted',
                                               detail={'questionCount': len(schema)}))
            emit_partner_event(session, org_id=role.org_id, event_type='application.submitted', data={
                **(assessment_request_context(session, application.id) if invitation else {}),
                'applicationId': str(application.id), 'roleId': str(role.id),
                'status': application.status,
                'externalCandidateId': invitation.external_candidate_id if invitation else None,
            })
        else:
            application.answers = answers
            application.location = location
            application.consented_at = _utcnow()
        if invitation and invitation.status != 'accepted':
            invitation.status = 'accepted'
            invitation.application_id = application.id
            invitation.accepted_at = _utcnow()
        sessions, _ = _sync_application(session, application)
        out = _application_view(application, sessions)
        out['returnUrl'] = invitation.return_url if invitation else None
    return jsonify(application=out, company=org.name), 201


@hiring_bp.route('/roles/<role_id>/my-application', methods=['GET'])
@require_auth
def my_application(role_id):
    rid = _uuid(role_id)
    with db_session() as session:
        application = (session.query(HiringApplication).filter_by(
            role_posting_id=rid, applicant_id=g.user_id).one_or_none()) if rid else None
        if not application:
            return jsonify(application=None), 200
        sessions, best = _sync_application(session, application)
        view = _application_view(application, sessions)
        view['employerUpdate'] = hiring_reviews.review_view(hiring_reviews.latest_events(session, application.id), public=True)
        view['bestAssessment'] = _assessment_report(best) if best else None
        view['latestAssessment'] = _latest_assessment(session, sessions)
        partner_request = (session.query(PartnerInvitation).filter_by(application_id=application.id)
                           .order_by(PartnerInvitation.created_at.desc()).first())
        view['returnUrl'] = partner_request.return_url if partner_request else None
        response = jsonify(application=view)
        response.headers['Cache-Control'] = 'no-store'
        return response, 200


@hiring_bp.route('/applications/<application_id>', methods=['GET'])
@require_auth
def get_application(application_id):
    aid = _uuid(application_id)
    with db_session() as session:
        application = session.get(HiringApplication, aid) if aid else None
        if not application or application.applicant_id != g.user_id:
            return jsonify(error='Not found'), 404
        sessions, best = _sync_application(session, application)
        view = _application_view(application, sessions)
        view['employerUpdate'] = hiring_reviews.review_view(hiring_reviews.latest_events(session, application.id), public=True)
        view['bestAssessment'] = _assessment_report(best) if best else None
        view['latestAssessment'] = _latest_assessment(session, sessions)
        partner_request = (session.query(PartnerInvitation).filter_by(application_id=application.id)
                           .order_by(PartnerInvitation.created_at.desc()).first())
        view['returnUrl'] = partner_request.return_url if partner_request else None
        role = session.get(RolePosting, application.role_posting_id)
        org = session.get(Org, role.org_id) if role else None
        view['role'] = {'id': str(role.id), 'title': role.title, 'status': role.status} if role else None
        view['company'] = {'name': org.name} if org else None
        response = jsonify(application=view)
        response.headers['Cache-Control'] = 'no-store'
        return response, 200


@hiring_bp.route('/my-applications', methods=['GET'])
@require_auth
@require_verified_email
def my_applications():
    """Applicant-owned summaries; invitations are not needed to resume an accepted application."""
    try:
        limit = max(1, min(40, int(request.args.get('limit', 20))))
        cursor = _decode_page_cursor(request.args.get('cursor'))
    except (TypeError, ValueError):
        return jsonify(error='Invalid application page'), 400
    with db_session() as session:
        query = (session.query(HiringApplication, RolePosting, Org)
                 .join(RolePosting, RolePosting.id == HiringApplication.role_posting_id)
                 .join(Org, Org.id == RolePosting.org_id)
                 .filter(HiringApplication.applicant_id == g.user_id))
        if cursor:
            submitted_at, application_id = cursor
            query = query.filter(or_(
                HiringApplication.submitted_at < submitted_at,
                and_(HiringApplication.submitted_at == submitted_at, HiringApplication.id < application_id)))
        rows = query.order_by(HiringApplication.submitted_at.desc(), HiringApplication.id.desc()).limit(limit + 1).all()
        has_more = len(rows) > limit
        rows = rows[:limit]
        response = jsonify(applications=[{
            'id': str(application.id), 'status': application.status,
            'submittedAt': application.submitted_at.isoformat(),
            'role': {'id': str(role.id), 'title': role.title, 'status': role.status},
            'company': {'name': org.name},
        } for application, role, org in rows],
            page={'nextCursor': _page_cursor(rows[-1][0]) if has_more else None})
        response.headers['Cache-Control'] = 'no-store'
        return response, 200


def _application_motion_criteria(session, application):
    criteria = hiring_motion_criteria(application.assessment_criteria)
    invitation = (session.query(PartnerInvitation).filter_by(application_id=application.id)
                  .order_by(PartnerInvitation.created_at.desc()).first())
    if invitation and (invitation.assessment_profile != PROFILE_ID or invitation.assessment_profile_version != VERSION):
        raise ValueError('This invitation requires assessment contract review.')
    return criteria


def _launch_url(session_id):
    assessment_url = os.environ.get('ASSESSMENT_PUBLIC_URL', 'https://cookcredit-knife-demo.web.app/').rstrip('/') + '/'
    if os.environ.get('ASSESSMENT_SAME_ORIGIN_ENABLED') == '1':
        assessment_url = os.environ['FRONTEND_URL'].split(',', 1)[0].rstrip('/') + '/landing/assessment/'
    api_origin = os.environ.get('PUBLIC_API_URL', '').rstrip('/')
    return_url = os.environ.get('FRONTEND_URL', '').split(',', 1)[0].rstrip('/')
    query = {'mode': 'test', 'hiringSession': str(session_id)}
    if api_origin:
        query['apiOrigin'] = api_origin
    if return_url:
        query['returnUrl'] = return_url + '/application-assessment-return/' + str(session_id)
    return assessment_url + '?' + urlencode(query)


@hiring_bp.route('/applications/<application_id>/attempts/start', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('10 per hour', key_func=lambda: g.user_id)
def start_attempt(application_id):
    if os.environ.get('ASSESSMENT_BRIDGE_ENABLED') == '0':
        return jsonify(error='The assessment connection is not enabled in this environment', code='assessment_unavailable'), 503
    aid = _uuid(application_id)
    with db_session() as session:
        application = (session.query(HiringApplication).filter_by(id=aid, applicant_id=g.user_id)
                       .with_for_update().one_or_none()) if aid else None
        if not application or application.status == 'withdrawn':
            return jsonify(error='Not found'), 404
        role = session.get(RolePosting, application.role_posting_id)
        if not role or role.status != 'open':
            return jsonify(error='This role is closed'), 409
        try:
            _application_motion_criteria(session, application)
        except ValueError as exc:
            return jsonify(error=str(exc), code='assessment_contract_review_required'), 409
        sessions, _ = _sync_application(session, application)
        active = next((s for s in sessions if s.status == 'started' and s.expires_at > _utcnow()), None)
        if active:
            return jsonify(sessionId=str(active.id), slot=active.slot,
                           launchUrl=_launch_url(active.id), expiresAt=active.expires_at.isoformat()), 200
        reserved = {s.slot for s in sessions if s.status in ('processing', 'completed')}
        slot = next((n for n in range(1, application.attempt_limit + 1) if n not in reserved), None)
        if slot is None:
            return jsonify(error='All assessment attempts have been used'), 409
        old = next((s for s in sessions if s.slot == slot and s.status == 'expired'), None)
        if old:
            session.delete(old)
            session.flush()
        item = HiringAssessmentSession(application_id=application.id, applicant_id=g.user_id,
                                       slot=slot, status='started', expires_at=_utcnow() + SESSION_TTL)
        session.add(item)
        session.flush()
        session.add(HiringApplicationEvent(application_id=application.id, actor_id=g.user_id,
                                           event_type='assessment_started', detail={'slot': slot}))
        emit_partner_event(session, org_id=role.org_id, event_type='assessment.started', data={
            **assessment_request_context(session, application.id),
            'applicationId': str(application.id), 'roleId': str(role.id),
            'sessionId': str(item.id), 'slot': slot, 'status': 'started',
        })
        return jsonify(sessionId=str(item.id), slot=slot, launchUrl=_launch_url(item.id),
                       expiresAt=item.expires_at.isoformat()), 201


@hiring_bp.route('/assessment-sessions/<session_id>/complete', methods=['POST'])
@require_auth
@require_verified_email
@require_app_check
@limiter.limit('10 per hour', key_func=lambda: g.user_id)
def complete_attempt(session_id):
    if request.content_length and request.content_length > landmark_recording.MAX_BYTES + 65536:
        return jsonify(error='Assessment submission is too large'), 413
    if os.environ.get('ASSESSMENT_BRIDGE_ENABLED') == '0':
        return jsonify(error='The assessment connection is not enabled in this environment', code='assessment_unavailable'), 503
    sid = _uuid(session_id)
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error='An assessment reference is required'), 400
    engine_id = str(body.get('assessmentId') or '')
    try:
        original_landmarks = landmark_recording.validate_landmarks(body.get('originalLandmarks'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    with db_session() as session:
        item = session.get(HiringAssessmentSession, sid) if sid else None
        if not item or item.applicant_id != g.user_id:
            return jsonify(error='Not found'), 404
        if item.status in ('processing', 'completed'):
            return jsonify(sessionId=str(item.id), attemptId=str(item.attempt_id), status=item.status), 200
        if item.status != 'started' or item.expires_at <= _utcnow():
            return jsonify(error='This assessment session has expired'), 409
        application = session.get(HiringApplication, item.application_id)
        role = session.get(RolePosting, application.role_posting_id) if application else None
        if not application or application.status == 'withdrawn' or not role or role.status != 'open':
            return jsonify(error='This application is no longer accepting assessments'), 409
        try:
            _application_motion_criteria(session, application)
        except ValueError as exc:
            return jsonify(error=str(exc), code='assessment_contract_review_required'), 409
    try:
        capture_claim = validate_capture(body.get('captureMetadata'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    try:
        if engine_recording_import.enabled():
            evidence = verified_engine_assessment(g.user_id, engine_id,
                id_token=request.headers['Authorization'].removeprefix('Bearer ').strip(),
                app_check=request.headers.get('X-Firebase-AppCheck'))
        else:
            evidence = verified_engine_assessment(g.user_id, engine_id)
    except InvalidEngineAssessment as exc:
        return jsonify(error=str(exc)), 409
    except Exception:
        return jsonify(error='Assessment verification is temporarily unavailable'), 503
    with db_session() as session:
        item = session.query(HiringAssessmentSession).filter_by(id=sid).with_for_update().one_or_none()
        if not item or item.applicant_id != g.user_id:
            return jsonify(error='Not found'), 404
        if item.status in ('processing', 'completed'):
            return jsonify(sessionId=str(item.id), attemptId=str(item.attempt_id), status=item.status), 200
        if item.status != 'started' or item.expires_at <= _utcnow():
            return jsonify(error='This assessment session has expired'), 409
        used = (session.query(HiringAssessmentSession).filter(
            HiringAssessmentSession.engine_assessment_id == engine_id,
            HiringAssessmentSession.id != item.id).first())
        if used:
            return jsonify(error='This assessment was already submitted to another attempt'), 409
        application = session.get(HiringApplication, item.application_id)
        role = session.get(RolePosting, application.role_posting_id) if application else None
        if not application or application.status == 'withdrawn' or not role or role.status != 'open':
            return jsonify(error='This application is no longer accepting assessments'), 409
        try:
            criteria = _application_motion_criteria(session, application)
        except ValueError as exc:
            return jsonify(error=str(exc), code='assessment_contract_review_required'), 409
        profile_id = PROFILE_ID
        meta = {**evidence['metadata'], 'recording_path': evidence['storagePath'],
                'recording_generation': evidence['generation'],
                'engine_assessment_id': evidence['assessmentId'], 'source': 'cookcredit-skill-live',
                'assessment_criteria': criteria,
                'assessment_profile_version': VERSION}
        if original_landmarks is not None:
            try:
                meta['original_landmarks'] = landmark_recording.save_landmarks(original_landmarks, evidence, g.user_id)
            except Exception:
                return jsonify(error='Original landmark storage failed. Retry this submission.'), 503
        if capture_claim is not None:
            meta['capture_evidence'] = bind_capture(capture_claim, evidence)
        score = evidence['onDevice'].get('score')
        score = float(score) if isinstance(score, (int, float)) and not isinstance(score, bool) else None
        attempt, _ = create_or_get_attempt(
            session, user_id=g.user_id, session_id='engine-' + engine_id,
            profile_id=profile_id, on_device_score=score,
            on_device_block=evidence['onDevice'], local_result={}, trajectory=[],
            metadata=meta, video_url=evidence['locator'])
        session.flush()
        item.engine_assessment_id = engine_id
        item.attempt_id = attempt.id
        item.status = 'processing'
        application.status = 'assessment_processing'
        session.add(HiringApplicationEvent(application_id=application.id, actor_id=g.user_id,
                                           event_type='assessment_uploaded',
                                           detail={'slot': item.slot, 'attemptId': str(attempt.id)}))
        role = session.get(RolePosting, application.role_posting_id)
        emit_partner_event(session, org_id=role.org_id, event_type='assessment.processing', data={
            **assessment_request_context(session, application.id),
            'applicationId': str(application.id), 'roleId': str(role.id),
            'attemptId': str(attempt.id), 'slot': item.slot,
        })
        return jsonify(sessionId=str(item.id), attemptId=str(attempt.id), status='processing'), 202


@hiring_bp.route('/assessment-sessions/<session_id>', methods=['GET'])
@require_auth
def get_assessment_session(session_id):
    """Applicant-owned handoff status used by the return page after camera capture."""
    sid = _uuid(session_id)
    with db_session() as session:
        item = session.get(HiringAssessmentSession, sid) if sid else None
        if not item or item.applicant_id != g.user_id:
            return jsonify(error='Not found'), 404
        application = session.get(HiringApplication, item.application_id)
        if not application:
            return jsonify(error='Not found'), 404
        sessions, best = _sync_application(session, application)
        current = next((candidate for candidate in sessions if candidate.id == item.id), item)
        attempt = session.get(SkillAttempt, current.attempt_id) if current.attempt_id else None
        payload = {
            'presentation': session_presentation(session, application),
            'sessionId': str(current.id), 'applicationId': str(application.id),
            'roleId': str(application.role_posting_id),
            'slot': current.slot, 'status': current.status,
            'attemptId': str(current.attempt_id) if current.attempt_id else None,
            'processingState': attempt.verification_state.lower() if attempt else None,
            'result': _assessment_report(attempt) if attempt and attempt.verification_state in ATTEMPT_TERMINAL else None,
            'bestAssessment': _assessment_report(best) if best else None,
        }
        response = jsonify(session=payload)
        response.headers['Cache-Control'] = 'no-store'
        return response, 200


@hiring_bp.route('/applications/<application_id>/withdraw', methods=['POST'])
@require_auth
@limiter.limit('10 per hour', key_func=lambda: g.user_id)
def withdraw_application(application_id):
    """Stop future employer access while preserving the audit trail."""
    aid = _uuid(application_id)
    with db_session() as session:
        application = (session.query(HiringApplication)
                       .filter_by(id=aid, applicant_id=g.user_id)
                       .with_for_update().one_or_none()) if aid else None
        if not application:
            return jsonify(error='Not found'), 404
        if application.status != 'withdrawn':
            application.status = 'withdrawn'
            now = _utcnow()
            (session.query(AssessmentShare)
             .filter_by(role_posting_id=application.role_posting_id,
                        applicant_id=application.applicant_id)
             .filter(AssessmentShare.revoked_at.is_(None))
             .update({'revoked_at': now}, synchronize_session=False))
            session.add(HiringApplicationEvent(
                application_id=application.id, actor_id=g.user_id,
                event_type='application_withdrawn', detail={'recordingAccessRevoked': True}))
            role = session.get(RolePosting, application.role_posting_id)
            emit_partner_event(session, org_id=role.org_id, event_type='application.withdrawn', data={
                **assessment_request_context(session, application.id),
                'applicationId': str(application.id), 'roleId': str(role.id), 'status': 'withdrawn',
            })
            emit_partner_event(session, org_id=role.org_id, event_type='assessment.withdrawn', data={
                **assessment_request_context(session, application.id),
                'applicationId': str(application.id), 'roleId': str(role.id), 'status': 'withdrawn',
            })
        sessions = (session.query(HiringAssessmentSession)
                    .filter_by(application_id=application.id).all())
        return jsonify(application=_application_view(application, sessions)), 200


@hiring_bp.route('/roles/<role_id>/applications', methods=['GET'])
@require_auth
def employer_applications(role_id):
    rid = _uuid(role_id)
    try:
        limit = max(1, min(100, int(request.args.get('limit', 40))))
    except (TypeError, ValueError):
        return jsonify(error='Invalid page limit'), 400
    outcome = str(request.args.get('outcome') or '').strip()
    if outcome and outcome not in ('demonstrated', 'not_demonstrated', 'review_required'):
        return jsonify(error='Invalid assessment outcome'), 400
    status = str(request.args.get('status') or '').strip()
    city = re.sub(r'\s+', ' ', str(request.args.get('city') or '').strip())[:120]
    if status and status not in APPLICATION_STATUSES:
        return jsonify(error='Invalid application status'), 400
    try:
        cursor = _decode_page_cursor(request.args.get('cursor'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    with db_session() as session:
        if not _can(session, g.user_id, 'candidates'):
            return jsonify(error='This seat cannot review candidates'), 403
        role = _role_owned(session, rid, g.user_id) if rid else None
        if not role:
            return jsonify(error='Not found'), 404
        query = session.query(HiringApplication).filter_by(role_posting_id=role.id)
        if outcome:
            query = query.filter(HiringApplication.screening_outcome == outcome, HiringApplication.status != 'withdrawn')
        if status:
            query = query.filter(HiringApplication.status == status)
        if city:
            query = query.filter(func.lower(HiringApplication.location['city'].astext) == city.casefold())
        if cursor:
            submitted_at, application_id = cursor
            query = query.filter(or_(
                HiringApplication.submitted_at < submitted_at,
                and_(HiringApplication.submitted_at == submitted_at,
                     HiringApplication.id < application_id),
            ))
        rows = (query.order_by(HiringApplication.submitted_at.desc(), HiringApplication.id.desc())
                .limit(limit + 1).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        application_ids = [item.id for item in rows]
        all_sessions = (session.query(HiringAssessmentSession)
                        .filter(HiringAssessmentSession.application_id.in_(application_ids))
                        .order_by(HiringAssessmentSession.started_at).all()) if application_ids else []
        sessions_by_application = {}
        for assessment_session in all_sessions:
            sessions_by_application.setdefault(assessment_session.application_id, []).append(assessment_session)
        attempt_ids = {item.attempt_id for item in all_sessions if item.attempt_id}
        attempts_by_id = {item.id: item for item in (
            session.query(SkillAttempt).filter(SkillAttempt.id.in_(attempt_ids)).all()
            if attempt_ids else [])}
        applicant_ids = {item.applicant_id for item in rows}
        users_by_id = {item.id: item for item in (
            session.query(User).filter(User.id.in_(applicant_ids)).all()
            if applicant_ids else [])}
        out = []
        for application in rows:
            sessions, best = _sync_application(
                session, application,
                prefetched_sessions=sessions_by_application.get(application.id, []),
                prefetched_attempts=attempts_by_id)
            user = users_by_id.get(application.applicant_id)
            item = _application_view(application, sessions)
            item['candidate'] = {'id': application.applicant_id, 'name': (application.applicant_details or {}).get('name') or (user.name if user else 'Applicant')}
            item['bestAssessment'] = (_assessment_report(best)
                                      if best and application.status != 'withdrawn' else None)
            latest = next((attempts_by_id.get(row.attempt_id) for row in reversed(sessions)
                           if row.status == 'completed' and row.attempt_id), None)
            item['latestAssessment'] = (_assessment_report(latest)
                                       if latest and application.status != 'withdrawn' else None)
            out.append(item)
        return jsonify(
            applications=out, role={'id': str(role.id), 'title': role.title},
            page={'limit': limit, 'nextCursor': _page_cursor(rows[-1]) if has_more and rows else None},
            filters={'status': status or None, 'city': city or None, 'outcome': outcome or None},
            ordering='submission_time_descending',
        ), 200


@hiring_bp.route('/applications/<application_id>/cv', methods=['GET'])
@require_auth
@require_verified_email
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def application_cv(application_id):
    aid = _uuid(application_id)
    with db_session() as session:
        application = session.get(HiringApplication, aid) if aid else None
        if not application:
            return jsonify(error='Not found'), 404
        owner = application.applicant_id == g.user_id
        # The applicant exemption must not restore a revoked employer's CV access.
        from services.hiring_access import enabled, employer_access_allowed
        if not owner and enabled() and not employer_access_allowed(g.email, g.user_id):
            return jsonify(error='Not found'), 404
        if not owner and (application.consent_version != APPLICATION_CONSENT_VERSION or application.status == 'withdrawn' or not _can(session, g.user_id, 'candidates')
                          or not _role_owned(session, application.role_posting_id, g.user_id)):
            return jsonify(error='Not found'), 404
        metadata = (application.applicant_details or {}).get('cv')
        if not metadata:
            return jsonify(error='Not found'), 404
        if not hiring_cv.available(metadata, application.submitted_at):
            return jsonify(error='This CV has expired under the 30-day retention policy.', code='cv_expired'), 410
        try:
            data = hiring_cv.download_cv(application.id, metadata)
        except hiring_cv.CvUnavailable as exc:
            return jsonify(error=str(exc), code='cv_unavailable'), 410
        except Exception:
            return jsonify(error='CV is temporarily unavailable. Please try again.'), 503
        session.add(HiringApplicationEvent(application_id=application.id, actor_id=g.user_id,
                                           event_type='cv_downloaded', detail={'owner': owner}))
    return Response(data, mimetype='application/pdf', headers={
        'Content-Disposition': 'attachment; filename="candidate-cv.pdf"',
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "sandbox; default-src 'none'",
    })


def _employer_review_access(session):
    from services.hiring_access import enabled, employer_access_allowed
    if (enabled() or os.environ.get('COOKCREDIT_ENVIRONMENT') == 'staging') and not employer_access_allowed(g.email, g.user_id):
        return False
    return _can(session, g.user_id, 'candidates')


@hiring_bp.route('/candidates/<cook_id>/applications', methods=['GET'])
@require_auth
@require_verified_email
@limiter.limit('120 per hour', key_func=lambda: g.user_id)
def candidate_applications(cook_id):
    with db_session() as session:
        if not _employer_review_access(session): return jsonify(error='Not found'), 404
        org = _org_for(session, g.user_id)
        if not org: return jsonify(error='Not found'), 404
        query = (session.query(HiringApplication, RolePosting)
                 .join(RolePosting, RolePosting.id == HiringApplication.role_posting_id)
                 .filter(RolePosting.org_id == org.id, RolePosting.integration_environment == 'live',
                         HiringApplication.applicant_id == cook_id,
                         HiringApplication.consent_version == APPLICATION_CONSENT_VERSION,
                         HiringApplication.status != 'withdrawn'))
        role_id = request.args.get('roleId')
        if role_id:
            rid = _uuid(role_id)
            if rid is None: return jsonify(error='Invalid role'), 400
            query = query.filter(RolePosting.id == rid)
        rows = query.order_by(HiringApplication.submitted_at.desc()).limit(100).all()
        result=[]
        for application, role in rows:
            events=hiring_reviews.latest_events(session, application.id)
            user=session.get(User, application.applicant_id)
            result.append({'id':str(application.id),'roleId':str(role.id),'roleTitle':role.title,
                'applicantName':(application.applicant_details or {}).get('name') or (user.name if user else ''),
                'hasCv':hiring_cv.available((application.applicant_details or {}).get('cv'), application.submitted_at),
                'questions':application.question_schema or [], 'answers':application.answers or {},
                'review':hiring_reviews.review_view(events, session=session),
                'employerUpdate':hiring_reviews.review_view(events, public=True)})
        response=jsonify(applications=result, canReview=_can(session,g.user_id,'decisions'))
        response.headers['Cache-Control']='private, no-store'
        return response


@hiring_bp.route('/applications/<application_id>/review', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('60 per hour', key_func=lambda: g.user_id)
def save_employer_review(application_id):
    body=request.get_json(silent=True)
    try: detail=hiring_reviews.validate_review(body)
    except ValueError as exc: return jsonify(error=str(exc)),400
    aid=_uuid(application_id)
    with db_session() as session:
        if not _employer_review_access(session) or not _can(session,g.user_id,'decisions'):
            return jsonify(error='Not found'),404
        application=(session.query(HiringApplication).filter_by(id=aid).with_for_update().one_or_none()) if aid else None
        if (not application or application.status=='withdrawn'
                or application.consent_version!=APPLICATION_CONSENT_VERSION
                or not _role_owned(session,application.role_posting_id,g.user_id)):
            return jsonify(error='Not found'),404
        events=hiring_reviews.latest_events(session,application.id)
        revision=str(events[0].id) if events else None
        if body.get('revision')!=revision:
            return jsonify(error='Another reviewer changed this application. Reload before saving.'),409
        if detail['status'] == 'shortlisted':
            from routes.business import _set_shortlisted
            role = session.get(RolePosting, application.role_posting_id)
            _set_shortlisted(session, role.org_id, application.applicant_id, True)
        if events and events[0].detail==detail and (events[0].event_type==hiring_reviews.EVENTS[1])==body['publish']:
            response = jsonify(review=hiring_reviews.review_view(events, session=session),employerUpdate=hiring_reviews.review_view(events,public=True))
            response.headers['Cache-Control'] = 'private, no-store'
            return response
        event=HiringApplicationEvent(application_id=application.id,actor_id=g.user_id,
            event_type=hiring_reviews.EVENTS[1 if body['publish'] else 0],detail=detail)
        session.add(event);session.flush()
        card=session.query(PipelineCard).filter_by(role_posting_id=application.role_posting_id,cook_id=application.applicant_id).one_or_none()
        stage={'reviewing':'verified','shortlisted':'shortlisted','contacted':'contacted','hired':'hired','not_selected':'not_selected'}[detail['status']]
        if card: card.stage=stage
        events.insert(0,event)
        response=jsonify(review=hiring_reviews.review_view(events, session=session),employerUpdate=hiring_reviews.review_view(events,public=True))
        response.headers['Cache-Control']='private, no-store'
        return response
