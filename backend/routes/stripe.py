"""
Stripe routes — Cook Connect onboarding + payment stubs.

Connect onboarding is needed early (Task 9 in plan). Booking payment
flows (authorize, capture, webhook) will be built in Tasks 17-19.

The old house-meal escrow/tip system has been completely removed.
"""

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
from sqlalchemy.dialects.postgresql import insert
from services.stripe_service import (
    create_connect_account, create_onboarding_link, get_account_status,
    get_cook_balance, construct_webhook_event, create_login_link,
    create_billing_customer, create_subscription_checkout, create_billing_portal,
    retrieve_billing_subscription, retrieve_billing_checkout,
)
from middleware.auth import require_auth, require_verified_email
from extensions import limiter
from services.database import db_session
from models import User, CookProfile, Org, StripeEvent
from routes.business import _can, _org_for
from services.integration_usage import current_usage

stripe_bp = Blueprint("stripe", __name__)
log = logging.getLogger(__name__)

ENTITLED_SUBSCRIPTION_STATUSES = {'active', 'trialing', 'past_due'}


@stripe_bp.before_request
def disabled_billing():
    # Stop new purchases without interrupting signed event reconciliation.
    if (os.environ.get('BUSINESS_BILLING_ENABLED') == '0'
            and request.endpoint not in ('stripe.webhook', 'stripe.dispatch_events')
            and request.method not in ('GET', 'OPTIONS')):
        return jsonify(error='Payments are not enabled in this environment', code='billing_unavailable'), 503


def _utcnow():
    return datetime.now(timezone.utc)


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _period_end(value):
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OSError):
        return None


def _metadata(obj):
    raw = obj.get('metadata') or {}
    return dict(raw) if hasattr(raw, 'items') else {}


def _org_for_billing_object(session, obj):
    if _metadata(obj).get('cookcredit_product') not in (None, 'hiring'):
        return None
    oid = _uuid(_metadata(obj).get('cookcredit_org_id') or obj.get('client_reference_id'))
    if oid:
        org = session.query(Org).filter_by(id=oid).with_for_update().one_or_none()
        if org:
            return org
    customer_id, subscription_id = obj.get('customer'), obj.get('subscription') or obj.get('id')
    if customer_id:
        org = session.query(Org).filter_by(stripe_customer_id=str(customer_id)).with_for_update().one_or_none()
        if org:
            return org
    if subscription_id:
        return session.query(Org).filter_by(stripe_subscription_id=str(subscription_id)).with_for_update().one_or_none()
    return None


class BillingReconciliationUnavailable(Exception):
    pass


@stripe_bp.errorhandler(BillingReconciliationUnavailable)
def billing_reconciliation_unavailable(_error):
    # The exception exits db_session first, rolling back both event claim and
    # account changes. A replay can then retry safely without a stuck event ID.
    return jsonify(error='Billing synchronization temporarily unavailable'), 503


def _subscription_id(value):
    value = value.get('id') if hasattr(value, 'get') else value
    return str(value) if value else None


def _reconcile_subscription(org, reference):
    """Read current Stripe state under the workspace lock, independent of delivery order."""
    incoming_id = _subscription_id(reference)
    if not incoming_id:
        return
    current_id = org.stripe_subscription_id
    try:
        subscription = retrieve_billing_subscription(current_id or incoming_id)
        if current_id and current_id != incoming_id:
            # A late event for an old subscription cannot replace a current one.
            # A newer subscription may replace one which has actually ended.
            if subscription.get('status') in ('canceled', 'incomplete_expired'):
                incoming = retrieve_billing_subscription(incoming_id)
                if int(incoming.get('created') or 0) > int(subscription.get('created') or 0):
                    subscription = incoming
        if os.environ.get('COOKCREDIT_ENVIRONMENT') == 'staging' and subscription.get('livemode') is not False:
            raise BillingReconciliationUnavailable()
        if (os.environ.get('K_SERVICE') and os.environ.get('COOKCREDIT_ENVIRONMENT') != 'staging'
                and subscription.get('livemode') is not True):
            raise BillingReconciliationUnavailable()
    except Exception:
        raise BillingReconciliationUnavailable() from None
    customer_id = _subscription_id(subscription.get('customer'))
    metadata_org = _metadata(subscription).get('cookcredit_org_id')
    if (_metadata(subscription).get('cookcredit_product') not in (None, 'hiring')
            or not customer_id or (org.stripe_customer_id and org.stripe_customer_id != customer_id)
            or (metadata_org and str(metadata_org) != str(org.id))
            or (subscription.get('id') != current_id and str(metadata_org) != str(org.id))):
        return
    _sync_subscription(org, subscription)


def _sync_subscription(org, subscription, *, deleted=False):
    status = 'canceled' if deleted else str(subscription.get('status') or 'incomplete')
    items = ((subscription.get('items') or {}).get('data') or [])
    price = ((items[0].get('price') or {}).get('id') if items else None)
    plan_by_price = {
        os.getenv('STRIPE_TEAM_PRICE_ID', '').strip(): 'team',
        os.getenv('STRIPE_INTEGRATION_PRICE_ID', '').strip(): 'integration',
    }
    plan_by_price.pop('', None)
    from sqlalchemy import inspect
    state = inspect(org, raiseerr=False)
    session = state.session if state is not None else None
    saved_price = None
    if session is not None:
        from services.billing_catalog import price_for_subscription
        saved_price = price_for_subscription(session, price)
        if saved_price: plan_by_price[price] = saved_price.plan

    if subscription.get('id') != org.stripe_subscription_id and price not in plan_by_price:
        return  # An unrelated product must not claim or downgrade a Hiring workspace.
    org.stripe_customer_id = str(subscription.get('customer') or org.stripe_customer_id or '') or None
    org.stripe_subscription_id = str(subscription.get('id') or org.stripe_subscription_id or '') or None
    org.subscription_status = status
    org.subscription_price_id = price or org.subscription_price_id
    org.subscription_period_end = _period_end(subscription.get('current_period_end')
        or (items[0].get('current_period_end') if items else None))
    org.subscription_cancel_at_period_end = bool(subscription.get('cancel_at_period_end'))
    org.billing_updated_at = _utcnow()
    entitled_plan = plan_by_price.get(price) if status in ENTITLED_SUBSCRIPTION_STATUSES else None
    if org.plan != 'enterprise':
        org.plan = entitled_plan or 'trial'
        org.subscription_limits = dict(saved_price.limits) if saved_price and entitled_plan else None


# ─── Business subscription billing ───────────────────────────────────────────

@stripe_bp.route('/business/status', methods=['GET'])
@require_auth
def business_billing_status():
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can manage billing'), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify(error='Workspace not found'), 404
        from services.billing_catalog import catalog
        prices = catalog(session)
        return jsonify(
            prices=prices, billingEnabled=os.getenv('BUSINESS_BILLING_ENABLED') == '1',
            plan=org.plan or 'trial', status=org.subscription_status,
            cancelAtPeriodEnd=bool(org.subscription_cancel_at_period_end),
            periodEnd=org.subscription_period_end.isoformat() if org.subscription_period_end else None,
            hasCustomer=bool(org.stripe_customer_id),
            checkoutConfigured=bool(prices and os.getenv('STRIPE_SECRET_KEY', '').strip()),
            integrationCheckoutConfigured=bool(any(p['plan'] == 'integration' for p in prices) and os.getenv('STRIPE_SECRET_KEY', '').strip()),
            teamPrice=os.getenv('STRIPE_TEAM_PRICE_DISPLAY', '$99'),
            integrationPrice=os.getenv('STRIPE_INTEGRATION_PRICE_DISPLAY', '$299'),
            integrationUsage=(current_usage(session, org=org)
                              if (org.plan or 'trial') in ('integration', 'enterprise') else None),
        ), 200


@stripe_bp.route('/business/checkout', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('10 per hour', key_func=lambda: g.user_id)
def business_checkout():
    if os.getenv('BUSINESS_BILLING_OWNER_ONLY') == '1':
        from services.hiring_access import is_owner
        if not is_owner(g.email):
            return jsonify(error='Subscriptions are not available for this workspace yet.'), 403
    body = request.get_json(silent=True) or {}
    request_id = _uuid(body.get('requestId'))
    plan = str(body.get('plan') or 'team').strip()
    interval = body.get('interval', 'month')
    if interval not in ('month','year'): return jsonify(error='Choose monthly or annual billing'), 400
    if not request_id:
        return jsonify(error='A valid checkout request id is required'), 400
    if plan not in ('team', 'integration'):
        return jsonify(error='plan must be team or integration'), 400
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can manage billing'), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify(error='Workspace not found'), 404
        org = session.query(Org).filter_by(id=org.id).with_for_update().populate_existing().one()
        if org.plan == 'enterprise':
            return jsonify(error='Enterprise billing is managed by contract'), 409
        if org.plan in ('team', 'integration') and org.stripe_subscription_id:
            return jsonify(error='Use the billing portal to change an active subscription'), 409
        from services.billing_catalog import current_price
        selected = current_price(session, plan, interval)
        if not selected:
            return jsonify(error='This subscription price is not available.'), 409
        if body.get('priceId') != str(selected.id):
            return jsonify(error='Pricing changed. Refresh the plans before checkout.'), 409
        selected_price_id = selected.stripe_price_id
        reservation = org.billing_checkout
        if not reservation:
            reservation = {'id': str(uuid.uuid4()), 'priceId': selected_price_id, 'plan': plan,
                           'createdAt': _utcnow().isoformat(), 'email': g.email, 'name': org.name}
            org.billing_checkout = reservation
        org_id, org_name, customer_id = str(org.id), reservation['name'], org.stripe_customer_id
    try:
        if reservation.get('sessionId'):
            previous = retrieve_billing_checkout(reservation['sessionId'])
            if previous.get('status') == 'open':
                if reservation['priceId'] != selected_price_id:
                    return jsonify(error='Another plan already has an open checkout. Finish it or let it expire first.'), 409
                return jsonify(checkoutUrl=previous['url'], sessionId=previous['id']), 200
            if previous.get('status') == 'expired':
                with db_session() as session:
                    org = session.query(Org).filter_by(id=_uuid(org_id)).with_for_update().one()
                    if org.billing_checkout and org.billing_checkout['id'] == reservation['id']:
                        org.billing_checkout = None
                return jsonify(error='The previous checkout expired. Please start checkout again.'), 409
            return jsonify(error='Payment is being synchronized. Refresh billing shortly.'), 409
        if reservation['priceId'] != selected_price_id:
            return jsonify(error='Another plan checkout is being prepared. Retry shortly.'), 409
        if _utcnow() - datetime.fromisoformat(reservation['createdAt']) >= timedelta(hours=23):
            # Never reuse an uncertain provider request beyond its idempotency
            # retention window. Reconcile it before permitting another charge.
            return jsonify(error='This checkout needs billing support before it can be retried.'), 409
        if not customer_id:
            customer_id = create_billing_customer(
                email=reservation['email'], name=org_name, org_id=org_id,
                idempotency_key=f'org:{org_id}:customer-v1')
            with db_session() as session:
                org = session.query(Org).filter_by(id=_uuid(org_id)).with_for_update().one()
                if not org.stripe_customer_id:
                    org.stripe_customer_id = customer_id
                    org.billing_updated_at = _utcnow()
                customer_id = org.stripe_customer_id
        checkout = create_subscription_checkout(
            customer_id=customer_id, org_id=org_id, request_id=reservation['id'], plan=plan, price_id=selected_price_id)
        with db_session() as session:
            org = session.query(Org).filter_by(id=_uuid(org_id)).with_for_update().one()
            if org.billing_checkout and org.billing_checkout['id'] == reservation['id']:
                org.billing_checkout = dict(reservation, sessionId=checkout['id'])
        return jsonify(checkoutUrl=checkout['url'], sessionId=checkout['id']), 201
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except Exception:
        log.exception('Business checkout creation failed for org %s', org_id)
        return jsonify(error='Checkout is temporarily unavailable'), 503


@stripe_bp.route('/business/portal', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('10 per hour', key_func=lambda: g.user_id)
def business_portal():
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can manage billing'), 403
        org = _org_for(session, g.user_id)
        if not org or not org.stripe_customer_id:
            return jsonify(error='No billing account exists for this workspace'), 409
        customer_id, org_id = org.stripe_customer_id, str(org.id)
    try:
        return jsonify(portalUrl=create_billing_portal(customer_id=customer_id)), 200
    except Exception:
        log.exception('Business billing portal failed for org %s', org_id)
        return jsonify(error='Billing portal is temporarily unavailable'), 503


# ─── Cook Connect Onboarding ─────────────────────────────────────────────────

@stripe_bp.route("/connect/onboard", methods=["POST"])
@require_auth
@limiter.limit("5 per hour", key_func=lambda: g.user_id)
def onboard_cook():
    with db_session() as session:
        cook = session.query(CookProfile).filter_by(user_id=g.user_id).first()
        if not cook:
            return jsonify({"error": "Cook profile not found"}), 404

        user = session.get(User, g.user_id)

        if cook.stripe_account_id:
            stripe_account_id = cook.stripe_account_id
        else:
            result = create_connect_account(g.email, user.name or "Cook")
            stripe_account_id = result["stripe_account_id"]
            cook.stripe_account_id = stripe_account_id
            cook.stripe_onboarded = False

        url = create_onboarding_link(stripe_account_id, g.user_id)
        return jsonify({"onboarding_url": url})


@stripe_bp.route("/connect/status", methods=["GET"])
@require_auth
@limiter.limit("30 per hour", key_func=lambda: g.user_id)
def connect_status():
    with db_session() as session:
        cook = session.query(CookProfile).filter_by(user_id=g.user_id).first()
        if not cook or not cook.stripe_account_id:
            return jsonify({"onboarded": False, "message": "No Stripe account yet"})

        status = get_account_status(cook.stripe_account_id)
        cook.stripe_onboarded = status["details_submitted"]
        status["account_id"] = cook.stripe_account_id
        return jsonify(status)


@stripe_bp.route("/connect/dashboard", methods=["POST"])
@require_auth
@limiter.limit("10 per hour", key_func=lambda: g.user_id)
def connect_dashboard():
    with db_session() as session:
        cook = session.query(CookProfile).filter_by(user_id=g.user_id).first()
        if not cook or not cook.stripe_account_id:
            return jsonify({"error": "No Stripe account found"}), 400
        try:
            url = create_login_link(cook.stripe_account_id)
            return jsonify({"url": url})
        except Exception:
            log.exception("connect_dashboard failed for user %s", g.user_id)
            return jsonify({"error": "Could not generate dashboard link"}), 400


@stripe_bp.route("/connect/balance", methods=["GET"])
@require_auth
@limiter.limit("30 per hour", key_func=lambda: g.user_id)
def cook_balance():
    with db_session() as session:
        cook = session.query(CookProfile).filter_by(user_id=g.user_id).first()
        if not cook or not cook.stripe_account_id:
            return jsonify({"error": "Cook has no Stripe account"}), 400
        return jsonify(get_cook_balance(cook.stripe_account_id))


# ─── Webhook ─────────────────────────────────────────────────────────────────

def _process_event(session, event_type, obj):
    if event_type == "account.updated":
        account_id = obj["id"]
        cook = session.query(CookProfile).filter_by(stripe_account_id=account_id).first()
        if cook:
            cook.stripe_onboarded = obj.get("details_submitted", False)

    elif event_type == 'checkout.session.completed' and obj.get('mode') == 'subscription':
        org = _org_for_billing_object(session, obj)
        if org:
            _reconcile_subscription(org, obj.get('subscription'))

    elif event_type in ('customer.subscription.created', 'customer.subscription.updated',
                        'customer.subscription.deleted'):
        org = _org_for_billing_object(session, obj)
        if org:
            _reconcile_subscription(org, obj.get('id'))

    elif event_type in ('invoice.paid', 'invoice.payment_failed'):
        org = _org_for_billing_object(session, obj)
        raw_subscription = obj.get('subscription') or ((obj.get('parent') or {}).get('subscription_details') or {}).get('subscription')
        invoice_subscription_id = _subscription_id(raw_subscription)
        # A customer can own unrelated Stripe products. Only the subscription
        # already verified by a subscription webhook may change this workspace.
        if org and invoice_subscription_id and str(invoice_subscription_id) == org.stripe_subscription_id:
            _reconcile_subscription(org, invoice_subscription_id)



@stripe_bp.route("/webhook", methods=["POST"])
@limiter.exempt
@limiter.limit("60 per minute")
def webhook():
    """
    Stripe webhook handler.

    Currently handles:
      account.updated → sync cook Connect onboarding status

    Booking payment events (payment_intent.succeeded, etc.) will be
    added in Task 19.
    """
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = construct_webhook_event(payload, sig_header)
    except ValueError:
        return jsonify({"error": "Invalid payload"}), 400
    except Exception:
        log.warning("Stripe webhook signature verification failed", exc_info=True)
        return jsonify({"error": "Webhook verification failed"}), 400

    event_id = str(event['id'])
    if os.environ.get('COOKCREDIT_ENVIRONMENT') == 'staging' and event.get('livemode') is not False:
        return jsonify(error='Staging accepts only Stripe test events'), 400
    if (os.environ.get('K_SERVICE') and os.environ.get('COOKCREDIT_ENVIRONMENT') != 'staging'
            and event.get('livemode') is not True):
        return jsonify(error='Production accepts only Stripe live events'), 400
    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type not in ('account.updated', 'checkout.session.completed',
                          'customer.subscription.created', 'customer.subscription.updated',
                          'customer.subscription.deleted', 'invoice.paid', 'invoice.payment_failed'):
        return jsonify(received=True, ignored=True), 200
    if _metadata(obj).get('cookcredit_product') not in (None, 'hiring'):
        return jsonify(received=True, ignored=True), 200
    if os.getenv('STRIPE_ASYNC_ENABLED') == '1':
        compact = {key: obj[key] for key in ('id', 'customer', 'subscription', 'client_reference_id',
                   'mode', 'details_submitted') if key in obj}
        for key in ('id', 'customer', 'subscription'):
            if key in compact:
                compact[key] = _subscription_id(compact[key])
        compact['metadata'] = {key: value for key, value in _metadata(obj).items()
                               if key in ('cookcredit_org_id', 'cookcredit_product')}
        if event_type.startswith('invoice.'):
            compact['subscription'] = _subscription_id(obj.get('subscription') or
                ((obj.get('parent') or {}).get('subscription_details') or {}).get('subscription'))
        with db_session() as session:
            claimed = session.execute(insert(StripeEvent).values(
                id=event_id, event_type=event_type, livemode=bool(event.get('livemode')),
                received_at=_utcnow(), processed_at=None, payload=compact, attempts=0,
                next_attempt_at=_utcnow())
                .on_conflict_do_nothing(index_elements=['id']).returning(StripeEvent.id)).scalar_one_or_none()
            if claimed:
                from services.webhook_dispatch import request_dispatch
                request_dispatch(session, _utcnow(), kind='billing')
        return jsonify(received=True, queued=bool(claimed), duplicate=not bool(claimed)), 200

    with db_session() as session:
        claimed = session.execute(insert(StripeEvent).values(
            id=event_id, event_type=event_type, livemode=bool(event.get('livemode')),
            received_at=_utcnow(), processed_at=_utcnow())
            .on_conflict_do_nothing(index_elements=['id']).returning(StripeEvent.id)).scalar_one_or_none()
        if claimed is None:
            return jsonify({'received': True, 'duplicate': True}), 200

        _process_event(session, event_type, obj)

    return jsonify({"received": True})


@stripe_bp.route('/internal/dispatch-events', methods=['POST'])
@limiter.exempt
def dispatch_events():
    from services.internal_auth import internal_request_authorized
    if not internal_request_authorized(request):
        return jsonify(error='Forbidden'), 403
    return jsonify(dispatch_billing_events())


def dispatch_billing_events(*, limit=5):
    """Bounded inbox drain. Row locks serialize workers; failed state stays retryable."""
    from services.webhook_dispatch import request_dispatch
    from services.operations import emit_event
    stats = {'processed': 0, 'retrying': 0, 'failed': 0}
    claimed = 0
    for _ in range(max(1, min(5, limit))):
        with db_session() as session:
            row = (session.query(StripeEvent)
                   .filter(StripeEvent.processed_at.is_(None), StripeEvent.payload.isnot(None),
                           StripeEvent.next_attempt_at <= _utcnow(), StripeEvent.attempts < 24)
                   .order_by(StripeEvent.next_attempt_at, StripeEvent.id)
                   .with_for_update(skip_locked=True).first())
            if row is None:
                break
            claimed += 1
            row.attempts += 1
            try:
                with session.begin_nested():
                    _process_event(session, row.event_type, row.payload)
                row.processed_at = _utcnow()
                row.payload = None
                row.last_error = None
                row.next_attempt_at = None
                stats['processed'] += 1
            except Exception:
                row.last_error = 'billing_reconciliation_failed'
                if row.attempts >= 24:
                    row.next_attempt_at = None
                    stats['failed'] += 1
                else:
                    row.next_attempt_at = _utcnow() + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts - 1, 7)))
                    request_dispatch(session, row.next_attempt_at, kind='billing')
                    stats['retrying'] += 1
    if claimed == max(1, min(5, limit)):
        with db_session() as session:
            request_dispatch(session, _utcnow(), kind='billing')
    with db_session() as session:
        failed = session.query(StripeEvent).filter(StripeEvent.processed_at.is_(None), StripeEvent.attempts >= 24).count()
    emit_event('billing_queue_health', severity='ERROR' if failed or stats['retrying'] else 'INFO',
               failed=failed, processed=stats['processed'], retrying=stats['retrying'])
    return stats
