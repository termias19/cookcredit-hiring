"""Home API. It is intentionally absent from the Hiring blueprint registry."""
import os
from functools import wraps
from flask import Blueprint, g, jsonify, request
from extensions import limiter
from middleware.auth import require_identity, require_verified_email
from services.database import db_session
from services import home_visits as visits
from services import home_quotes as quotes
from services import home_payments as payments, home_stripe
from models.home_service import HomeEvent
from sqlalchemy import select

home_bp = Blueprint('home_visits', __name__)


def emails(setting):
    return {e.strip().casefold() for e in os.getenv(setting, '').split(',') if e.strip()}


def is_owner():
    return g.email.casefold() in emails('HOME_OWNER_EMAILS')


def is_operator():
    return is_owner() or g.email.casefold() in emails('HOME_OPERATOR_EMAILS')


def home_auth(f):
    # Identity is shared; company approval, Hiring seats and self-selected User
    # roles confer no Home operator or helper privileges.
    @wraps(f)
    @require_identity
    @require_verified_email
    def decorated(*args, **kwargs):
        if not g.email:
            visits.fail('email_required', 'A verified email is required.', 403)
        if os.getenv('COOKCREDIT_ENVIRONMENT')=='staging' and os.getenv('HOME_ACCEPTANCE_EMAILS','') and g.email.casefold() not in emails('HOME_ACCEPTANCE_EMAILS'):
            visits.fail('private_acceptance','This account is not enabled for private Home acceptance.',403)
        return f(*args, **kwargs)
    return decorated


def principal():
    return {'uid': g.user_id, 'email': g.email, 'name': g.name}


def json_body():
    body = request.get_json()
    if not isinstance(body, dict):
        visits.fail('invalid_json', 'Please check the request fields.')
    return body


@home_bp.get('/me')
@home_auth
@limiter.limit('60 per minute', key_func=lambda: g.user_id)
def me():
    # Cook onboarding/approval is separate from creating an inert customer identity.
    with db_session() as session:
        visits.sync_identity(session, principal())
        from models.home_service import HomeHelperPermission
        helper = session.get(HomeHelperPermission, g.user_id)
        from services.home_mail import ensure_welcome
        ensure_welcome(session,principal())
        from services import home_operating_rules as rules
        policy=rules.active(session,required=False)
        service_rules=policy['rules'] if policy else rules.defaults()
    return jsonify(userId=g.user_id, name=g.name, email=g.email, operator=is_operator(), owner=is_owner(),
                   helper=bool(helper and helper.enabled),
                   consentVersion=visits.CONSENT_VERSION, consentText=visits.CONSENT_TEXT,
                   paymentsAvailable=home_stripe.checkout_allowed(),environment=os.getenv('COOKCREDIT_ENVIRONMENT','development'),
                   serviceTimeZone=service_rules['timeZone'] if policy else os.getenv('HOME_SERVICE_TIMEZONE','America/New_York'),
                   serviceStates=service_rules['states'])


@home_bp.post('/visits')
@home_auth
@limiter.limit('10 per minute', key_func=lambda: g.user_id)
def create():
    body, actor = json_body(), principal()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'create', body,
            lambda: visits.create_visit(session, actor, body))
    return jsonify(result), 201


@home_bp.get('/visits')
@home_auth
@limiter.limit('60 per minute', key_func=lambda: g.user_id)
def listing():
    with db_session() as session:
        result = visits.list_visits(session, g.user_id, is_operator(), request.args.get('cursor'))
    return jsonify(result)


@home_bp.get('/visits/<booking_id>')
@home_auth
@limiter.limit('60 per minute', key_func=lambda: g.user_id)
def detail(booking_id):
    with db_session() as session:
        booking, visit = visits.load_visit(session, booking_id, g.user_id, is_operator())
        result = visits.serialize(booking, visit, detail=True)
        result['quote'] = quotes.quote_for_visit(session, booking, visit, g.user_id, is_operator())
        result['payment'] = payments.dto(session, booking, visit, payments.payment_for_visit(session, booking['id']), g.user_id, is_operator())
        from models import User
        from services.home_customers import audit
        helper_name=session.execute(select(User.name).where(User.id==booking['cook_id'])).scalar() if booking['cook_id'] else None
        result['helperName']=helper_name
        result['isCustomer']=booking['eater_id']==g.user_id
        result['isAssignedHelper']=booking['cook_id']==g.user_id
        if is_operator():
            result['customerId']=booking['eater_id']
        if is_operator() or (booking['cook_id']==g.user_id and booking['eater_id']!=g.user_id):
            audit(session,principal(),'visit_viewed',booking['id'])
    return jsonify(result)


@home_bp.post('/visits/<booking_id>/actions')
@home_auth
@limiter.limit('20 per minute', key_func=lambda: g.user_id)
def action(booking_id):
    body, actor, operator = json_body(), principal(), is_operator()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'action:' + booking_id,
            body, lambda: visits.transition(session, actor, booking_id, body, operator))
    return jsonify(result)


@home_bp.put('/helpers/<helper_id>/permission')
@home_auth
@limiter.limit('20 per minute', key_func=lambda: g.user_id)
def helper_permission(helper_id):
    if not is_owner():
        visits.fail('forbidden', 'Only the Home owner can change helper permissions.', 403)
    body, actor = json_body(), principal()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'permission:' + helper_id,
            body, lambda: visits.set_helper_permission(session, actor, helper_id, body))
    return jsonify(result)


@home_bp.get('/visits/<booking_id>/activity')
@home_auth
@limiter.limit('60 per minute', key_func=lambda: g.user_id)
def activity(booking_id):
    if not is_operator():
        visits.fail('forbidden', 'CookCredit operator access is required.', 403)
    with db_session() as session:
        booking, _ = visits.load_visit(session, booking_id, g.user_id, True)
        # Bounded page using a monotone booking version (each accepted command
        # emits exactly one event). No note, email, token or address is serialized.
        after = request.args.get('afterVersion', '-1')
        try:
            after = int(after)
            if after < -1:
                raise ValueError()
        except ValueError:
            visits.fail('invalid_cursor', 'Please refresh the activity list.')
        events = session.execute(select(HomeEvent).where(HomeEvent.booking_id == booking['id'],
            HomeEvent.version > after).order_by(HomeEvent.version).limit(100)).scalars().all()
        result = [{'action': e.action, 'version': e.version, 'at': e.created_at.isoformat(),
                   'actorId': e.actor_id, 'details': e.details} for e in events]
    return jsonify(events=result, nextAfterVersion=result[-1]['version'] if len(result) == 100 else None)


@home_bp.get('/pricing')
@home_auth
@limiter.limit('30 per minute', key_func=lambda: g.user_id)
def pricing():
    if not is_operator():
        visits.fail('forbidden', 'CookCredit operator access is required.', 403)
    with db_session() as session:
        result = quotes.pricing(session)
    return jsonify(result)


@home_bp.post('/pricing')
@home_auth
@limiter.limit('20 per minute', key_func=lambda: g.user_id)
def save_pricing():
    if not is_owner():
        visits.fail('forbidden', 'Only the Home owner can set prices.', 403)
    body, actor = json_body(), principal()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'pricing:create',
            body, lambda: quotes.save_rates(session, actor, body))
    return jsonify(result), 201


@home_bp.post('/pricing/<rate_card_id>/activate')
@home_auth
@limiter.limit('20 per minute', key_func=lambda: g.user_id)
def activate_pricing(rate_card_id):
    if not is_owner():
        visits.fail('forbidden', 'Only the Home owner can activate prices.', 403)
    body, actor = json_body(), principal()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'pricing:activate:' + rate_card_id,
            body, lambda: quotes.activate_rates(session, actor, rate_card_id, body))
    return jsonify(result)


@home_bp.post('/visits/<booking_id>/quotes')
@home_auth
@limiter.limit('20 per minute', key_func=lambda: g.user_id)
def issue_quote(booking_id):
    if not is_operator():
        visits.fail('forbidden', 'Only CookCredit can issue quotes.', 403)
    body, actor = json_body(), principal()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'quote:create:' + booking_id,
            body, lambda: quotes.issue_quote(session, actor, booking_id, body, True))
    return jsonify(result), 201


@home_bp.get('/visits/<booking_id>/quotes/<quote_id>')
@home_auth
@limiter.limit('60 per minute', key_func=lambda: g.user_id)
def historical_quote(booking_id, quote_id):
    operator = is_operator()
    with db_session() as session:
        booking, visit = visits.load_visit(session, booking_id, g.user_id, operator)
        result = quotes.quote_for_visit(session, booking, visit, g.user_id, operator, quote_id)
    return jsonify(quote=result)


@home_bp.post('/visits/<booking_id>/quotes/<quote_id>/<any(accept,approve):decision>')
@home_auth
@limiter.limit('20 per minute', key_func=lambda: g.user_id)
def approve_quote(booking_id, quote_id, decision):
    body, actor, operator = json_body(), principal(), is_operator()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'),
            'quote:' + decision + ':' + booking_id + ':' + quote_id, body,
            lambda: quotes.accept_quote(session, actor, booking_id, quote_id, body, operator, helper=decision == 'accept'))
    return jsonify(result)


@home_bp.post('/visits/<booking_id>/materials/reconcile')
@home_auth
@limiter.limit('20 per minute', key_func=lambda: g.user_id)
def reconcile_materials(booking_id):
    if not is_operator():
        visits.fail('forbidden', 'Only CookCredit can reconcile receipts.', 403)
    body, actor = json_body(), principal()
    from services.home_receipts import verified_references
    with db_session() as session:
        prior = visits.replay(session, actor, request.headers.get('Idempotency-Key'), 'materials:reconcile:' + booking_id, body)
    if prior is not None:
        return jsonify(prior)
    proof=verified_references(booking_id,body.get('quoteId'),body.get('lines',[]))
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'materials:reconcile:' + booking_id,
            body, lambda: quotes.reconcile_materials(session, actor, booking_id, body, True, evidence=proof))
    return jsonify(result)


@home_bp.post('/visits/<booking_id>/checkout')
@home_auth
@limiter.limit('10 per minute', key_func=lambda: g.user_id)
def checkout(booking_id):
    body, actor, operator = json_body(), principal(), is_operator()
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'checkout:' + booking_id,
            body, lambda: payments.prepare_checkout(session, actor, booking_id, body, operator))
    return jsonify(result), 202


@home_bp.post('/visits/<booking_id>/payment/refresh')
@home_auth
@limiter.limit('4 per minute', key_func=lambda: g.user_id)
def refresh_payment(booking_id):
    body, actor = json_body(), principal()
    visits.strict_object(body, ())
    with db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'), 'payment-refresh:' + booking_id,
            body, lambda: payments.refresh_payment(session, actor, booking_id, is_operator()))
    return jsonify(result), 202


@home_bp.post('/stripe/webhook')
@limiter.exempt
def stripe_webhook():
    from services.home_finance_worker import receive_event
    request.max_content_length = 256 * 1024
    try:
        event = home_stripe.StripeHome().verify(request.get_data(cache=False), request.headers.get('Stripe-Signature', ''))
    except Exception:
        return jsonify(error='Invalid webhook signature'), 400
    with db_session() as session:
        result = receive_event(session, event)
    return jsonify(result)


@home_bp.post('/internal/dispatch')
@limiter.exempt
def internal_dispatch():
    from services.internal_auth import internal_request_authorized
    from services.home_finance_worker import dispatch_events, dispatch_operations
    if not internal_request_authorized(request):
        return jsonify(error='Forbidden'), 403
    events = dispatch_events(limit=5) if home_stripe.mode() != 'off' else {'paused':True}
    operations = dispatch_operations(limit=5) if home_stripe.mode() != 'off' else {'paused':True}
    from services.home_mail import convert_events
    from services.account_email import dispatch_account_emails
    notifications=convert_events()
    mail=dispatch_account_emails(limit=5) if os.getenv('HOME_EMAILS_ENABLED')=='1' else {'paused':True}
    from services.operations import report_queue_health
    healthy=report_queue_health('email') if os.getenv('HOME_EMAILS_ENABLED')=='1' else None
    from services.home_dispatch import request_next
    # If the outbox is full and SMTP made no progress, do not wake every two
    # seconds while provider retries are delayed. Eligible account mail keeps
    # its own earlier deadline; only unconverted Home notices back off.
    from datetime import datetime, timedelta, timezone
    notice_retry = (datetime.now(timezone.utc) + timedelta(seconds=30)
        if notifications.get('backpressured') and not (mail.get('sent',0) + mail.get('skipped',0)) else None)
    with db_session() as session:
        request_next(session, notifications_not_before=notice_retry)
    return jsonify(events=events, operations=operations,notifications=notifications,mail=mail,healthy=healthy)


@home_bp.get('/operations')
@home_auth
@limiter.limit('12 per minute', key_func=lambda: g.user_id)
def financial_operations():
    if not is_owner():
        visits.fail('forbidden', 'Home owner access is required.', 403)
    from models.home_service import HomeFinancialOperation
    with db_session() as session:
        rows = session.execute(select(HomeFinancialOperation).order_by(HomeFinancialOperation.created_at.desc()).limit(100)).scalars().all()
        result = [{'id': str(row.id), 'kind': row.kind, 'status': row.status, 'lastError': row.last_error,
                   'bookingId': str(row.booking_id) if row.booking_id else None, 'createdAt': row.created_at.isoformat()} for row in rows]
    return jsonify(operations=result)
