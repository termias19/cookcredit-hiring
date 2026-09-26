"""Enterprise API keys, assessment invitations, and signed webhook management."""
import hashlib
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import Blueprint, g, jsonify, request
from itsdangerous import URLSafeTimedSerializer, BadSignature
from sqlalchemy import tuple_

from extensions import limiter
from middleware.auth import require_auth
from models import (
    HiringApplication, Org, PartnerApiKey, PartnerInvitation, PartnerWebhook,
    PartnerWebhookDelivery, SkillAttempt,
    RolePosting,
)
from routes.business import _assessment_report, _can, _org_for
from services.database import db_session
from services.hiring_presentation import assessment_instructions
from services.hiring_applications import sync_application
from services.assessment_outcomes import evaluate_assessment, normalize_criteria
from services.live_motion_evidence import VERSION, PROFILE_ID, normalize_motion_criteria, hiring_motion_criteria
from services.partner_integrations import (
    VALID_SCOPES, WEBHOOK_EVENTS, decrypt_webhook_secret, dispatch_partner_webhooks,
    emit_partner_event, encrypt_webhook_secret, issue_api_key, require_partner_scope, validate_webhook_url,
)
from services.internal_auth import internal_request_authorized
from services.integration_usage import consume_request
from services.integration_access import integration_access

partner_bp = Blueprint('partner', __name__)


def _utcnow():
    return datetime.now(timezone.utc)


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _enterprise_org(session):
    if not _can(session, g.user_id, 'billing'):
        return None, (jsonify(error='Only a workspace admin can manage API integrations'), 403)
    org = _org_for(session, g.user_id)
    if not org:
        return None, (jsonify(error='Workspace not found'), 404)
    if not integration_access(org)['api']:
        return None, (jsonify(error='Integration plan required', upgradeRequired=True), 403)
    return org, None


def _key_view(key):
    return {
        'id': str(key.id), 'name': key.name, 'prefix': key.key_prefix,
        'scopes': key.scopes or [], 'createdAt': key.created_at.isoformat(),
        'environment': key.environment or 'live',
        'lastUsedAt': key.last_used_at.isoformat() if key.last_used_at else None,
        'revokedAt': key.revoked_at.isoformat() if key.revoked_at else None,
    }


@partner_bp.route('/manage/api-keys', methods=['GET', 'POST'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def api_keys():
    with db_session() as session:
        org, error = _enterprise_org(session)
        if error:
            return error
        if request.method == 'GET':
            rows = (session.query(PartnerApiKey).filter_by(org_id=org.id)
                    .order_by(PartnerApiKey.created_at.desc()).limit(100).all())
            return jsonify(keys=[_key_view(row) for row in rows]), 200
        body = request.get_json(silent=True) or {}
        name = re.sub(r'\s+', ' ', str(body.get('name') or '').strip())[:100]
        scopes = body.get('scopes') or []
        environment = str(body.get('environment') or 'live').strip()
        if (not name or not isinstance(scopes, list) or not scopes
                or any(not isinstance(scope, str) or scope not in VALID_SCOPES for scope in scopes)
                or environment not in ('test', 'live')):
            return jsonify(error='Name and valid scopes are required'), 400
        key, raw = issue_api_key(org_id=org.id, name=name, scopes=scopes,
                                 created_by=g.user_id, environment=environment)
        session.add(key); session.flush()
        return jsonify(key={**_key_view(key), 'secret': raw}), 201


@partner_bp.route('/manage/api-keys/<key_id>/revoke', methods=['POST'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def revoke_api_key(key_id):
    kid = _uuid(key_id)
    with db_session() as session:
        org, error = _enterprise_org(session)
        if error:
            return error
        key = session.query(PartnerApiKey).filter_by(id=kid, org_id=org.id).with_for_update().one_or_none() if kid else None
        if not key:
            return jsonify(error='Not found'), 404
        key.revoked_at = key.revoked_at or _utcnow()
        return jsonify(key=_key_view(key)), 200


@partner_bp.route('/manage/webhooks', methods=['GET', 'POST'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def webhooks():
    with db_session() as session:
        org, error = _enterprise_org(session)
        if error:
            return error
        if request.method == 'GET':
            rows = session.query(PartnerWebhook).filter_by(org_id=org.id).order_by(PartnerWebhook.created_at.desc()).all()
            return jsonify(webhooks=[{
                'id': str(row.id), 'url': row.url, 'eventTypes': row.event_types or [],
                'environment': row.environment,
                'active': row.active, 'failureCount': row.failure_count,
                'createdAt': row.created_at.isoformat(),
            } for row in rows]), 200
        body = request.get_json(silent=True) or {}
        try:
            url = validate_webhook_url(body.get('url'))
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        events = body.get('eventTypes')
        environment = body.get('environment', 'live')
        if (not isinstance(events, list) or not events
                or any(not isinstance(event, str) or event not in WEBHOOK_EVENTS for event in events)):
            return jsonify(error='Choose one or more supported webhook events'), 400
        if environment not in ('test', 'live'):
            return jsonify(error='environment must be test or live'), 400
        events = sorted(set(events))
        session.query(Org).filter_by(id=org.id).with_for_update().one()
        if session.query(PartnerWebhook).filter_by(org_id=org.id, environment=environment, url=url).first():
            return jsonify(error='This webhook URL already exists in this environment'), 409
        raw_secret = 'whsec_' + secrets.token_urlsafe(32)
        try:
            ciphertext = encrypt_webhook_secret(raw_secret)
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 503
        hook = PartnerWebhook(org_id=org.id, url=url, event_types=events, environment=environment,
                              secret_ciphertext=ciphertext, created_by=g.user_id)
        session.add(hook); session.flush()
        return jsonify(webhook={
            'id': str(hook.id), 'url': hook.url, 'eventTypes': hook.event_types,
            'active': True, 'secret': raw_secret, 'environment': environment,
        }), 201


@partner_bp.route('/manage/webhooks/<webhook_id>', methods=['PATCH'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def update_webhook(webhook_id):
    hook_id = _uuid(webhook_id)
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get('active'), bool):
        return jsonify(error='active must be true or false'), 400
    with db_session() as session:
        org, error = _enterprise_org(session)
        if error:
            return error
        hook = (session.query(PartnerWebhook).filter_by(id=hook_id, org_id=org.id)
                .with_for_update().one_or_none()) if hook_id else None
        if not hook:
            return jsonify(error='Not found'), 404
        hook.active = body['active']
        hook.disabled_at = None if hook.active else _utcnow()
        if hook.active:
            hook.failure_count = 0
        return jsonify(webhook={
            'id': str(hook.id), 'url': hook.url, 'eventTypes': hook.event_types or [],
            'active': hook.active, 'failureCount': hook.failure_count,
            'environment': hook.environment,
            'createdAt': hook.created_at.isoformat(),
        }), 200


def _delivery_view(row, hook):
    return {
        'id': str(row.id), 'webhookId': str(row.webhook_id), 'url': hook.url,
        'environment': hook.environment,
        'eventId': str(row.event_id), 'eventType': row.event_type,
        'status': row.status, 'attempts': row.attempts,
        'nextAttemptAt': row.next_attempt_at.isoformat() if row.next_attempt_at else None,
        'deliveredAt': row.delivered_at.isoformat() if row.delivered_at else None,
        'lastError': row.last_error, 'createdAt': row.created_at.isoformat(),
    }


@partner_bp.route('/manage/webhook-deliveries', methods=['GET'])
@require_auth
@limiter.limit('60 per hour', key_func=lambda: g.user_id)
def webhook_deliveries():
    with db_session() as session:
        org, error = _enterprise_org(session)
        if error:
            return error
        query = (session.query(PartnerWebhookDelivery, PartnerWebhook)
                 .join(PartnerWebhook, PartnerWebhook.id == PartnerWebhookDelivery.webhook_id)
                 .filter(PartnerWebhook.org_id == org.id))
        status = str(request.args.get('status') or '').strip()
        if status:
            query = query.filter(PartnerWebhookDelivery.status == status)
        rows = query.order_by(PartnerWebhookDelivery.created_at.desc()).limit(200).all()
        return jsonify(deliveries=[_delivery_view(row, hook) for row, hook in rows]), 200


@partner_bp.route('/manage/webhook-deliveries/<delivery_id>/replay', methods=['POST'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def replay_webhook_delivery(delivery_id):
    did = _uuid(delivery_id)
    with db_session() as session:
        org, error = _enterprise_org(session)
        if error:
            return error
        pair = (session.query(PartnerWebhookDelivery, PartnerWebhook)
                .join(PartnerWebhook, PartnerWebhook.id == PartnerWebhookDelivery.webhook_id)
                .filter(PartnerWebhookDelivery.id == did, PartnerWebhook.org_id == org.id)
                .with_for_update().one_or_none()) if did else None
        if not pair:
            return jsonify(error='Not found'), 404
        row, hook = pair
        if not hook.active:
            return jsonify(error='Enable this webhook before replaying a delivery'), 409
        row.status = 'pending'; row.attempts = 0; row.next_attempt_at = _utcnow()
        row.lock_token = None; row.locked_until = None; row.delivered_at = None; row.last_error = None
        return jsonify(delivery=_delivery_view(row, hook)), 200


@partner_bp.route('/v1/roles', methods=['GET'])
@require_partner_scope('roles:read')
def partner_roles():
    with db_session() as session:
        rows = (session.query(RolePosting).filter_by(org_id=g.partner_org_id,
                                                   integration_environment=g.partner_environment)
                .filter(RolePosting.integration_managed.is_(False))
                .order_by(RolePosting.created_at.desc()).limit(200).all())
        return jsonify(data=[role.to_dict() for role in rows]), 200


def _invitation_view(invitation, *, include_token=None):
    origin = os.getenv('FRONTEND_URL', 'http://localhost:5173').split(',', 1)[0].rstrip('/')
    result = {
        'id': str(invitation.id), 'roleId': str(invitation.role_posting_id),
        'externalCandidateId': invitation.external_candidate_id, 'status': invitation.status,
        'environment': invitation.environment,
        'expiresAt': invitation.expires_at.isoformat(),
        'applicationId': str(invitation.application_id) if invitation.application_id else None,
    }
    if include_token:
        result['invitationUrl'] = f'{origin}/apply/{invitation.role_posting_id}?invite={include_token}'
    return result


def _return_url(value):
    if value in (None, ''):
        return None
    clean = str(value).strip()[:1000]
    try:
        parsed = urlsplit(clean)
    except ValueError:
        raise ValueError('returnUrl is invalid')
    allow_http = os.environ.get('FLASK_ENV') == 'development' and parsed.hostname in ('localhost', '127.0.0.1')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and allow_http):
        raise ValueError('returnUrl must use HTTPS')
    if not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('returnUrl is invalid')
    return clean


def _request_status(session, item):
    now = _utcnow()
    if item.status == 'canceled':
        return 'withdrawn', [], None
    if not item.application_id and item.expires_at <= now:
        if item.status != 'expired':
            item.status = 'expired'
            emit_partner_event(session, org_id=item.org_id, event_type='assessment.expired', data={
                'assessmentRequestId': str(item.id), 'externalCandidateId': item.external_candidate_id,
                'externalJobId': item.external_job_id, 'status': 'expired',
                'environment': item.environment,
            })
        return 'expired', [], None
    if not item.application_id:
        return 'invited', [], None
    application = session.get(HiringApplication, item.application_id)
    if not application:
        return 'invited', [], None
    sessions, best = sync_application(session, application)
    if application.status == 'withdrawn':
        return 'withdrawn', sessions, best
    if application.status == 'ready':
        return 'evidence_ready', sessions, best
    if any(row.status == 'processing' for row in sessions):
        return 'processing', sessions, best
    if any(row.status == 'started' for row in sessions):
        return 'started', sessions, best
    return 'applied', sessions, best


def _assessment_request_view(session, item, *, include_token=None):
    status, sessions, best = _request_status(session, item)
    result_attempt = best
    if result_attempt is None and status == 'evidence_ready':
        completed = [row for row in sessions if row.status == 'completed' and row.attempt_id]
        if completed:
            result_attempt = session.get(SkillAttempt, completed[-1].attempt_id)
    origin = os.getenv('FRONTEND_URL', 'http://localhost:5173').split(',', 1)[0].rstrip('/')
    result = {
        'id': str(item.id), 'status': status,
        'roleId': str(item.role_posting_id), 'externalJobId': item.external_job_id,
        'jobTitle': item.job_title, 'externalCandidateId': item.external_candidate_id,
        'candidateEmail': item.candidate_email,
        'assessmentProfile': item.assessment_profile,
        'assessmentProfileVersion': item.assessment_profile_version,
        'attemptLimit': item.attempt_limit, 'returnUrl': item.return_url,
        'environment': item.environment, 'expiresAt': item.expires_at.isoformat(),
        'createdAt': item.created_at.isoformat(),
        'applicationId': str(item.application_id) if item.application_id else None,
        'attempts': [{'slot': row.slot, 'status': row.status,
                      'attemptId': str(row.attempt_id) if row.attempt_id else None}
                     for row in sessions],
        'assessmentCriteria': (item.request_config or {}).get('assessmentCriteria') or normalize_criteria(),
        'result': session.get(HiringApplication, item.application_id).screening_result if status == 'evidence_ready' else None,
        'review': ({'decision': item.review_decision, 'reason': item.review_reason,
                    'reviewedAt': item.reviewed_at.isoformat() if item.reviewed_at else None}
                   if item.review_decision else None),
    }
    if include_token:
        result['assessmentUrl'] = f'{origin}/apply/{item.role_posting_id}?invite={include_token}'
    return result


def _integration_role(session, *, org_id, external_job_id, job_title, attempt_limit,
                      profile, profile_version, questions, location_label, environment):
    # The caller holds the organization lock through idempotency and usage accounting.
    role = (session.query(RolePosting).filter_by(
        org_id=org_id, external_job_id=external_job_id,
        integration_environment=environment).one_or_none())
    requirements = {
        'integrationManaged': True, 'externalJobId': external_job_id,
        'applicationQuestions': questions, 'attemptLimit': attempt_limit,
        'assessmentProfile': profile, 'assessmentProfileVersion': profile_version,
        'locationLabel': location_label,
    }
    if role:
        role.title = job_title
        role.status = 'open'
        role.requirements = {**(role.requirements or {}), **requirements}
        return role
    role = RolePosting(
        org_id=org_id, title=job_title, status='open', requirements=requirements,
        external_job_id=external_job_id, integration_managed=True, integration_environment=environment,
    )
    session.add(role); session.flush()
    return role


def _questions(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError('applicationQuestions must be an array of at most 20 questions')
    out, seen = [], set()
    kinds = {'short_text', 'long_text', 'yes_no', 'select', 'multiselect', 'phone'}
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError('Each application question must be an object')
        qid = str(raw.get('id') or '').strip()[:50]
        label = re.sub(r'\s+', ' ', str(raw.get('label') or '').strip())[:200]
        kind = str(raw.get('type') or '')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,49}', qid) or qid in seen or not label or kind not in kinds:
            raise ValueError('One or more application questions are invalid')
        raw_options = raw.get('options') or []
        if not isinstance(raw_options, list) or any(not isinstance(x, str) for x in raw_options):
            raise ValueError('Question options must be an array of strings')
        options = [re.sub(r'\s+', ' ', x.strip())[:120] for x in raw_options]
        options = [x for x in options if x]
        if kind in ('select', 'multiselect') and not 2 <= len(options) <= 20:
            raise ValueError('Choice questions require 2 to 20 options')
        seen.add(qid)
        out.append({'id': qid, 'label': label, 'type': kind,
                    'required': bool(raw.get('required')), 'options': options})
    return out


def _fingerprint(endpoint, values):
    return hashlib.sha256(json.dumps(
        {'endpoint': endpoint, **values}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _request_assessment(body):
    """New partner requests use the published motion contract, never legacy defaults."""
    profile = body.get('assessmentProfile')
    version = body.get('assessmentProfileVersion')
    if profile is not None and profile != PROFILE_ID:
        raise ValueError('New hiring requests require the wrist_motion assessment profile')
    if version is not None and version != VERSION:
        raise ValueError('New hiring requests require the knife-motion-v1 assessment version')
    criteria = body.get('assessmentCriteria')
    if criteria is None:
        criteria = {}
    if not isinstance(criteria, dict):
        raise ValueError('assessmentCriteria must be an object')
    return PROFILE_ID, VERSION, normalize_motion_criteria({'profileVersion': VERSION, **criteria})


@partner_bp.route('/v1/assessment-requests', methods=['POST'])
@require_partner_scope('assessments:write')
def create_assessment_request():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(error='Assessment request must be an object'), 400
    email = str(body.get('candidateEmail') or '').strip().lower()[:320]
    external_candidate_id = str(body.get('externalCandidateId') or '').strip()[:200] or None
    external_job_id = str(body.get('externalJobId') or '').strip()[:200]
    job_title = re.sub(r'\s+', ' ', str(body.get('jobTitle') or '').strip())[:200]
    idem = str(request.headers.get('Idempotency-Key') or '').strip()
    environment = str(body.get('environment') or getattr(g, 'partner_environment', 'live')).strip()
    try:
        attempt_limit = int(body.get('attemptLimit', 3))
        questions = _questions(body.get('applicationQuestions'))
        instructions = assessment_instructions(body.get('assessmentInstructions'))
        return_url = _return_url(body.get('returnUrl'))
        profile, profile_version, criteria = _request_assessment(body)
    except (TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    location_label = re.sub(r'\s+', ' ', str(body.get('locationLabel') or '').strip())[:160] or None
    if (not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or not external_job_id
            or not job_title or not 8 <= len(idem) <= 200):
        return jsonify(error='externalJobId, jobTitle, candidateEmail, and Idempotency-Key are required'), 400
    if attempt_limit not in (1, 2, 3) or environment not in ('test', 'live'):
        return jsonify(error='attemptLimit must be 1 to 3 and environment must be test or live'), 400
    if environment != getattr(g, 'partner_environment', 'live'):
        return jsonify(error='Request environment must match the API key environment'), 400
    request_config = {'applicationQuestions': questions, 'locationLabel': location_label, 'assessmentCriteria': criteria}
    if instructions is not None:
        request_config['assessmentInstructions'] = instructions
    fingerprint = _fingerprint('assessment-requests', {
        'candidateEmail': email, 'externalCandidateId': external_candidate_id,
        'externalJobId': external_job_id, 'jobTitle': job_title, 'assessmentProfile': profile,
        'assessmentProfileVersion': profile_version, 'attemptLimit': attempt_limit,
        'returnUrl': return_url, 'environment': environment, **request_config,
    })
    with db_session() as session:
        # Lock before checking the key: concurrent retries must observe the committed
        # invitation, and quota consumption must share this same transaction.
        org = session.query(Org).filter_by(id=g.partner_org_id).with_for_update().one()
        existing = session.query(PartnerInvitation).filter_by(
            org_id=g.partner_org_id, environment=environment, idempotency_key=idem).one_or_none()
        if existing:
            if existing.request_fingerprint and existing.request_fingerprint != fingerprint:
                return jsonify(error='Idempotency-Key was already used for different request details',
                               code='idempotency_conflict'), 409
            try:
                token = decrypt_webhook_secret(existing.token_ciphertext)
            except RuntimeError:
                return jsonify(error='Assessment request cannot be recovered'), 503
            return jsonify(data=_assessment_request_view(session, existing, include_token=token)), 200
        try:
            usage = consume_request(session, org=org, environment=environment)
        except ValueError as exc:
            return jsonify(error=str(exc), code='monthly_limit_reached'), 429
        role = _integration_role(
            session, org_id=g.partner_org_id, external_job_id=external_job_id,
            job_title=job_title, attempt_limit=attempt_limit, profile=profile,
            profile_version=profile_version, questions=questions, location_label=location_label,
            environment=environment)
        token = 'cci_' + secrets.token_urlsafe(32)
        item = PartnerInvitation(
            org_id=g.partner_org_id, role_posting_id=role.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            token_ciphertext=encrypt_webhook_secret(token), candidate_email=email,
            external_candidate_id=external_candidate_id, external_job_id=external_job_id,
            job_title=job_title, assessment_profile=profile,
            assessment_profile_version=profile_version, attempt_limit=attempt_limit,
            return_url=return_url, environment=environment, idempotency_key=idem,
            request_fingerprint=fingerprint, request_config=request_config,
            expires_at=_utcnow() + timedelta(days=7))
        session.add(item); session.flush()
        event_data = {
            'assessmentRequestId': str(item.id), 'externalCandidateId': external_candidate_id,
            'externalJobId': external_job_id, 'roleId': str(role.id), 'status': 'invited',
            'assessmentProfile': profile, 'assessmentProfileVersion': profile_version,
            'environment': environment,
        }
        emit_partner_event(session, org_id=item.org_id, event_type='assessment.requested', data=event_data)
        emit_partner_event(session, org_id=item.org_id, event_type='assessment.invited', data=event_data)
        return jsonify(data=_assessment_request_view(session, item, include_token=token), usage=usage), 201


@partner_bp.route('/v1/assessment-requests', methods=['GET'])
@require_partner_scope('assessments:read')
def list_assessment_requests():
    filters = {key: str(request.args.get(key) or '')[:200]
               for key in ('externalJobId', 'externalCandidateId', 'status')}
    try:
        limit = int(request.args.get('limit', 100))
        if not 1 <= limit <= 100:
            raise ValueError()
        signer = URLSafeTimedSerializer(os.environ['PARTNER_API_KEY_PEPPER'], salt='assessment-list-v1')
        scope = [str(g.partner_org_id), g.partner_environment, filters]
        raw_cursor = request.args.get('cursor')
        position = None
        if raw_cursor:
            if len(raw_cursor) > 4096:
                raise ValueError()
            payload = signer.loads(raw_cursor, max_age=86400)
            if not isinstance(payload, dict) or payload.get('scope') != scope:
                raise ValueError()
            timestamp = datetime.fromisoformat(payload['at'])
            row_id = uuid.UUID(payload['id'])
            if timestamp.tzinfo is None:
                raise ValueError()
            position = (timestamp, row_id)
    except (ValueError, TypeError, KeyError, BadSignature):
        return jsonify(error='Invalid or expired pagination parameters'), 400
    with db_session() as session:
        query = session.query(PartnerInvitation).filter_by(org_id=g.partner_org_id,
                                                         environment=g.partner_environment)
        if filters['externalJobId']:
            query = query.filter_by(external_job_id=filters['externalJobId'])
        if filters['externalCandidateId']:
            query = query.filter_by(external_candidate_id=filters['externalCandidateId'])
        if position:
            query = query.filter(tuple_(PartnerInvitation.created_at, PartnerInvitation.id) < tuple_(*position))
        rows = query.order_by(PartnerInvitation.created_at.desc(), PartnerInvitation.id.desc()).with_for_update().limit(limit + 1).all()
        page = rows[:limit]
        data = [_assessment_request_view(session, row) for row in page]
        wanted = filters['status']
        if wanted:
            data = [row for row in data if row['status'] == wanted]
        # Status is derived from assessment sessions. Bound work per page even
        # when none match, and retain a cursor so clients can continue scanning.
        next_cursor = (signer.dumps({'scope': scope, 'at': page[-1].created_at.isoformat(),
                                    'id': str(page[-1].id)}) if len(rows) > limit else None)
        return jsonify(data=data, nextCursor=next_cursor, hasMore=bool(next_cursor)), 200


@partner_bp.route('/v1/assessment-requests/<request_id>', methods=['GET'])
@require_partner_scope('assessments:read')
def get_assessment_request(request_id):
    rid = _uuid(request_id)
    with db_session() as session:
        item = session.query(PartnerInvitation).filter_by(
            id=rid, org_id=g.partner_org_id, environment=g.partner_environment).with_for_update().one_or_none() if rid else None
        if not item:
            return jsonify(error='Not found'), 404
        return jsonify(data=_assessment_request_view(session, item)), 200


@partner_bp.route('/v1/assessment-requests/<request_id>/cancel', methods=['POST'])
@require_partner_scope('assessments:write')
def cancel_assessment_request(request_id):
    rid = _uuid(request_id)
    with db_session() as session:
        item = (session.query(PartnerInvitation).filter_by(id=rid, org_id=g.partner_org_id,
                                                        environment=g.partner_environment)
                .with_for_update().one_or_none()) if rid else None
        if not item:
            return jsonify(error='Not found'), 404
        if item.application_id:
            return jsonify(error='An accepted request must be withdrawn by the applicant'), 409
        if item.status not in ('canceled', 'expired'):
            item.status = 'canceled'; item.canceled_at = _utcnow()
            emit_partner_event(session, org_id=item.org_id, event_type='assessment.withdrawn', data={
                'assessmentRequestId': str(item.id), 'externalCandidateId': item.external_candidate_id,
                'externalJobId': item.external_job_id, 'status': 'withdrawn',
                'environment': item.environment,
            })
        return jsonify(data=_assessment_request_view(session, item)), 200


@partner_bp.route('/v1/assessment-requests/<request_id>/review', methods=['POST'])
@require_partner_scope('assessments:write')
def review_assessment_request(request_id):
    rid = _uuid(request_id)
    body = request.get_json(silent=True) or {}
    decision = str(body.get('decision') or '').strip()
    reason = re.sub(r'\s+', ' ', str(body.get('reason') or '').strip())[:1000] or None
    if decision not in ('advance', 'hold', 'decline'):
        return jsonify(error='decision must be advance, hold, or decline'), 400
    with db_session() as session:
        item = (session.query(PartnerInvitation).filter_by(id=rid, org_id=g.partner_org_id,
                                                        environment=g.partner_environment)
                .with_for_update().one_or_none()) if rid else None
        if not item:
            return jsonify(error='Not found'), 404
        status, _, _ = _request_status(session, item)
        if status != 'evidence_ready':
            return jsonify(error='Evidence must be ready before review is recorded'), 409
        item.review_decision = decision; item.review_reason = reason; item.reviewed_at = _utcnow()
        emit_partner_event(session, org_id=item.org_id, event_type='assessment.review_completed', data={
            'assessmentRequestId': str(item.id), 'externalCandidateId': item.external_candidate_id,
            'externalJobId': item.external_job_id, 'decision': decision,
            'environment': item.environment,
            'reason': reason, 'reviewedAt': item.reviewed_at.isoformat(),
        })
        return jsonify(data=_assessment_request_view(session, item)), 200


@partner_bp.route('/v1/assessment-invitations', methods=['POST'])
@require_partner_scope('invitations:write')
def create_assessment_invitation():
    body = request.get_json(silent=True) or {}
    role_id = _uuid(body.get('roleId'))
    email = str(body.get('candidateEmail') or '').strip().lower()[:320]
    external_id = str(body.get('externalCandidateId') or '').strip()[:200] or None
    idem = str(request.headers.get('Idempotency-Key') or '').strip()
    if not role_id or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or not 8 <= len(idem) <= 200:
        return jsonify(error='roleId, candidateEmail, and Idempotency-Key are required'), 400
    fingerprint = _fingerprint('assessment-invitations', {
        'roleId': str(role_id), 'candidateEmail': email, 'externalCandidateId': external_id,
    })
    with db_session() as session:
        org = session.query(Org).filter_by(id=g.partner_org_id).with_for_update().one()
        role = session.query(RolePosting).filter_by(
            id=role_id, org_id=g.partner_org_id, status='open',
            integration_environment=g.partner_environment, integration_managed=False).one_or_none()
        if not role:
            return jsonify(error='Role not found or closed'), 404
        existing = session.query(PartnerInvitation).filter_by(
            org_id=g.partner_org_id, environment=g.partner_environment, idempotency_key=idem).one_or_none()
        if existing:
            if existing.request_fingerprint and existing.request_fingerprint != fingerprint:
                return jsonify(error='Idempotency-Key was already used for different request details',
                               code='idempotency_conflict'), 409
            try:
                token = decrypt_webhook_secret(existing.token_ciphertext)
            except RuntimeError:
                return jsonify(error='Invitation cannot be recovered'), 503
            return jsonify(data=_invitation_view(existing, include_token=token)), 200
        requirements = role.requirements or {}
        try:
            criteria = hiring_motion_criteria(requirements.get('assessmentCriteria'), skill_floor=requirements.get('skillFloor'))
        except ValueError as exc:
            return jsonify(error=str(exc), code='assessment_contract_review_required'), 409
        try:
            consume_request(session, org=org, environment=g.partner_environment)
        except ValueError as exc:
            return jsonify(error=str(exc), code='monthly_limit_reached'), 429
        token = 'cci_' + secrets.token_urlsafe(32)
        invitation = PartnerInvitation(
            org_id=g.partner_org_id, role_posting_id=role.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            token_ciphertext=encrypt_webhook_secret(token), candidate_email=email,
            external_candidate_id=external_id, idempotency_key=idem,
            assessment_profile=PROFILE_ID, assessment_profile_version=VERSION,
            environment=g.partner_environment, request_fingerprint=fingerprint,
            attempt_limit=max(1, min(3, int(requirements.get('attemptLimit') or 3))),
            request_config={'applicationQuestions': requirements.get('applicationQuestions') or [],
                            'locationLabel': requirements.get('locationLabel'),
                            'assessmentInstructions': requirements.get('assessmentInstructions'),
                            'assessmentCriteria': criteria},
            expires_at=_utcnow() + timedelta(days=7))
        session.add(invitation); session.flush()
        return jsonify(data=_invitation_view(invitation, include_token=token)), 201


@partner_bp.route('/v1/applications/<application_id>', methods=['GET'])
@require_partner_scope('applications:read')
def partner_application(application_id):
    aid = _uuid(application_id)
    with db_session() as session:
        application = session.get(HiringApplication, aid) if aid else None
        role = session.get(RolePosting, application.role_posting_id) if application else None
        if (not application or not role or role.org_id != g.partner_org_id
                or role.integration_environment != g.partner_environment):
            return jsonify(error='Not found'), 404
        sessions, best = sync_application(session, application)
        invitation = (session.query(PartnerInvitation).filter_by(application_id=application.id)
                      .order_by(PartnerInvitation.created_at.desc()).first())
        result_attempt = best
        if result_attempt is None:
            completed = [item for item in sessions if item.status == 'completed' and item.attempt_id]
            if completed:
                result_attempt = session.get(SkillAttempt, completed[-1].attempt_id)
        return jsonify(data={
            'id': str(application.id), 'roleId': str(role.id), 'status': application.status,
            'environment': role.integration_environment,
            'attempts': [{'slot': item.slot, 'status': item.status} for item in sessions],
            'assessment': _assessment_report(best) if best and application.status != 'withdrawn' else None,
            'result': application.screening_result if application.status == 'ready' else None,
            'assessmentRequestId': str(invitation.id) if invitation else None,
            'externalCandidateId': invitation.external_candidate_id if invitation else None,
            'externalJobId': invitation.external_job_id if invitation else None,
            'submittedAt': application.submitted_at.isoformat(),
        }), 200


@partner_bp.route('/internal/dispatch-webhooks', methods=['POST'])
@limiter.exempt
def internal_dispatch_webhooks():
    if not internal_request_authorized(request):
        return jsonify(error='Forbidden'), 403
    return jsonify(dispatch_partner_webhooks(limit=50)), 200


@partner_bp.route('/internal/expire-assessment-requests', methods=['POST'])
@limiter.exempt
def internal_expire_assessment_requests():
    """Scheduler target: make expiration events proactive instead of waiting for an API read."""
    if not internal_request_authorized(request):
        return jsonify(error='Forbidden'), 403
    now = _utcnow()
    with db_session() as session:
        rows = (session.query(PartnerInvitation)
                .filter(PartnerInvitation.status == 'pending',
                        PartnerInvitation.application_id.is_(None),
                        PartnerInvitation.expires_at <= now)
                .order_by(PartnerInvitation.expires_at)
                .with_for_update(skip_locked=True).limit(500).all())
        for item in rows:
            item.status = 'expired'
            emit_partner_event(session, org_id=item.org_id, event_type='assessment.expired', data={
                'assessmentRequestId': str(item.id), 'externalCandidateId': item.external_candidate_id,
                'externalJobId': item.external_job_id, 'status': 'expired',
                'environment': item.environment,
            })
        return jsonify(expired=len(rows)), 200
