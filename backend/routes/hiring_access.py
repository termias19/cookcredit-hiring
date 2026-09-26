import uuid
from functools import wraps
from flask import Blueprint, g, jsonify, request
from sqlalchemy import tuple_
from extensions import limiter
from middleware.auth import require_auth, require_verified_email
from middleware.app_check import require_app_check
from models.hiring_access import HiringAccessRequest, HiringAccessEvent, HiringAccessInbox
from models.account_email import AccountEmail
from services.database import db_session
from services import hiring_access as access

access_bp = Blueprint('hiring_access', __name__)


@access_bp.post('/internal/sync-inbox')
@limiter.exempt
def sync_inbox():
    # Separate job: inbox latency/failures cannot delay account verification mail.
    from services.internal_auth import internal_request_authorized
    if not internal_request_authorized(request):
        return jsonify(error='Forbidden'), 403
    from services.hiring_access_inbox import sync_hiring_inbox
    result = sync_hiring_inbox()
    return jsonify(result), 503 if result.get('failed') else 200


def owner_only(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not access.enabled() or not access.is_owner(g.email, g.email_verified):
            return jsonify(error='Only the CookCredit owner can manage access.'), 403
        return fn(*args, **kwargs)
    return wrapped


@access_bp.post('/requests')
@limiter.limit('5 per hour;2 per minute')
@require_app_check
def request_access():
    if not access.enabled():
        return jsonify(error='Please email connectwithus@cookcredit.com to request access.'), 503
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Enter your request details.'), 400
    if data.get('website'):  # Honeypot. Do not send anything or disclose the trap.
        return jsonify(accepted=True), 202
    if data.get('contactConsent') is not True:
        return jsonify(error='Please allow us to contact you about this access request.'), 400
    try:
        with db_session() as session:
            access.create_request(session, data, source='website')
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    # No account existence or previous decision is disclosed to anonymous callers.
    return jsonify(accepted=True), 202


@access_bp.get('/owner/requests')
@require_auth
@require_verified_email
@owner_only
def list_requests():
    status = request.args.get('status', 'pending')
    if status not in ('pending', 'approved', 'declined', 'revoked', 'all'):
        return jsonify(error='Invalid status.'), 400
    with db_session() as session:
        query = session.query(HiringAccessRequest)
        if status != 'all':
            query = query.filter_by(status=status)
        if request.args.get('cursor'):
            try:
                previous = session.get(HiringAccessRequest, uuid.UUID(request.args['cursor']))
            except ValueError:
                previous = None
            if previous is None:
                return jsonify(error='Invalid cursor.'), 400
            query = query.filter(tuple_(HiringAccessRequest.created_at, HiringAccessRequest.id)
                                 < (previous.created_at, previous.id))
        rows = query.order_by(HiringAccessRequest.created_at.desc(), HiringAccessRequest.id.desc()).limit(51).all()
        output = []
        for row in rows[:50]:
            item = row.to_dict()
            mail = session.query(AccountEmail).filter_by(access_request_id=row.id, kind='access_approved').order_by(
                AccountEmail.created_at.desc()).first()
            item['invitationEmail'] = mail.status if mail else 'not_requested'
            output.append(item)
        from services.hiring_access_inbox import MAILBOXES
        mailboxes = []
        for address, _ in MAILBOXES:
            inbox = session.get(HiringAccessInbox, address)
            mailboxes.append({'address': address,
                'checkedAt': inbox.checked_at.isoformat() if inbox and inbox.checked_at else None,
                'error': inbox.last_error if inbox else None})
        import os
        return jsonify(requests=output, nextCursor=str(rows[49].id) if len(rows) > 50 else None,
                       inbox={'enabled': os.getenv('HIRING_ACCESS_INBOX_ENABLED') == '1',
                              'mailboxes': mailboxes})


@access_bp.post('/owner/requests')
@require_auth
@require_verified_email
@owner_only
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def add_request():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Enter the request details.'), 400
    try:
        with db_session() as session:
            row, created = access.create_request(session, data, source='owner', actor_id=g.user_id)
            return jsonify(request=row.to_dict()), 201 if created else 200
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@access_bp.post('/owner/requests/<request_id>/decision')
@require_auth
@require_verified_email
@owner_only
@limiter.limit('60 per hour;10 per minute', key_func=lambda: g.user_id)
def decision(request_id):
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        return jsonify(error='Request not found.'), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or type(data.get('sendEmail', False)) is not bool:
        return jsonify(error='Invalid decision.'), 400
    with db_session() as session:
        row = session.query(HiringAccessRequest).filter_by(id=rid).with_for_update().one_or_none()
        if row is None:
            return jsonify(error='Request not found.'), 404
        try:
            access.decide(session, row, action=data.get('action'), revision=data.get('revision'),
                          actor_id=g.user_id, send_email=data.get('sendEmail', False))
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
        session.flush()
        return jsonify(request=row.to_dict())


@access_bp.get('/owner/requests/<request_id>/events')
@require_auth
@require_verified_email
@owner_only
def events(request_id):
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        return jsonify(error='Request not found.'), 404
    with db_session() as session:
        rows = session.query(HiringAccessEvent).filter_by(request_id=rid).order_by(
            HiringAccessEvent.created_at.desc()).limit(100).all()
        return jsonify(events=[dict(action=row.action, actorId=row.actor_id,
                                    createdAt=row.created_at.isoformat()) for row in rows])
