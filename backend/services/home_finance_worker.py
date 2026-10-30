"""Leased Home financial outbox and signed event inbox.

Claim/commit -> bounded provider I/O -> fenced apply. Never hold a database
connection over Stripe calls; ambiguous old mutations require review, not a new key.
"""
import uuid
from datetime import timedelta
from sqlalchemy import select, update, or_, and_
from sqlalchemy.dialects.postgresql import insert
from models import Booking, CookProfile
from models.home_service import HomeVisit, HomePayment, HomeFinancialOperation as Op, HomeStripeEvent
from services.database import db_session
from services import home_visits as visits, home_payments as money, home_stripe
from services.operations import emit_event


class Deferred(Exception):
    def __init__(self, code, *, held=False):
        self.code, self.held = code, held


def _claim(model):
    stamp = money.now()
    with db_session() as session:
        row = session.execute(select(model).where(or_(
            and_(model.status.in_(('pending','retry')), model.available_at <= stamp),
            and_(model.status == 'running', model.lease_until < stamp)))
            .order_by(model.available_at, model.id).with_for_update(skip_locked=True).limit(1)).scalar_one_or_none()
        if not row:
            return None
        row.status, row.lease_token, row.lease_until = 'running', uuid.uuid4(), stamp + timedelta(minutes=3)
        row.attempts += 1
        if isinstance(row, Op) and not row.first_started_at:
            row.first_started_at = stamp
        return row


def _context(session, row):
    payment = session.get(HomePayment, row.payment_id)
    booking, visit = visits.load_visit(session, payment.booking_id, money.SYSTEM, True, lock=True)
    payment = session.get(HomePayment, row.payment_id, populate_existing=True, with_for_update=True)
    return payment, booking, visit


def _check_mode(payment, provider):
    if bool(provider.livemode) != payment.livemode:
        raise RuntimeError('mode_mismatch')


def _metadata(value):
    return value.get('metadata') or {}


def _validate_session(payment, value):
    metadata = _metadata(value)
    if (value.get('livemode') is not payment.livemode or value.get('mode') != 'payment'
        or metadata.get('cookcredit_product') != home_stripe.PRODUCT
        or metadata.get('home_payment_id') != str(payment.id)
        or metadata.get('home_quote_id') != str(payment.quote_id)
        or value.get('amount_total') != payment.amount_cents or value.get('currency') != 'usd'):
        raise RuntimeError('payment_binding_mismatch')


def _bump(session, booking, visit, action, payment):
    visit.version += 1
    visits.event(session, money.SYSTEM, action, booking['id'], visit.version, paymentId=str(payment.id))


def _sync_payment(session, payment, booking, visit, value):
    if str(_metadata(value).get('home_checkout_attempt')) != str(payment.checkout_attempt):
        return  # A delayed event for an expired, replaced checkout attempt.
    _validate_session(payment, value)
    payment.checkout_id = value['id']
    intent = value.get('payment_intent')
    if isinstance(intent, str):
        if value.get('payment_status') == 'paid':
            raise RuntimeError('expanded_payment_required')
        payment.payment_intent_id = intent
        intent = {}
    intent = intent or {}
    if intent:
        if (_metadata(intent).get('home_payment_id') != str(payment.id)
            or _metadata(intent).get('cookcredit_product') != home_stripe.PRODUCT
            or _metadata(intent).get('home_quote_id') != str(payment.quote_id)
            or intent.get('amount') != payment.amount_cents or intent.get('currency') != 'usd'
            or intent.get('livemode') is not payment.livemode):
            raise RuntimeError('intent_binding_mismatch')
        payment.payment_intent_id = intent['id']
        session.execute(update(Booking).where(Booking.id == booking['id']).values(stripe_payment_intent_id=intent['id']))
    charge = intent.get('latest_charge') or {}
    if isinstance(charge, str):
        raise RuntimeError('expanded_charge_required')
    if value.get('payment_status') == 'paid' and intent.get('status') == 'succeeded':
        if (not charge or charge.get('amount') != payment.amount_cents or charge.get('currency') != 'usd'
            or charge.get('livemode') is not payment.livemode or charge.get('paid') is not True
            or charge.get('payment_intent') != payment.payment_intent_id):
            raise RuntimeError('charge_binding_mismatch')
        first_paid = payment.paid_at is None
        payment.charge_id, payment.paid_at = charge['id'], payment.paid_at or money.now()
        payment.refunded_cents = int(charge.get('amount_refunded') or 0)
        if payment.refunded_cents > payment.amount_cents:
            raise RuntimeError('invalid_refund_total')
        payment.disputed = payment.disputed or bool(charge.get('disputed'))
        payment.status = 'refunded' if payment.refunded_cents == payment.amount_cents else 'paid'
        if first_paid:
            if booking['status'] == 'accepted' and not visit.issue_open:
                booking['status'] = 'confirmed'
                session.execute(update(Booking).where(Booking.id == booking['id']).values(status='confirmed'))
            _bump(session, booking, visit, 'payment_verified', payment)
        if payment.disputed:
            visit.issue_open = True
        if booking['status'] == 'cancelled':
            money.cancel_payment(session, booking, visit, payment)
        money.ensure_settlement(session, booking, visit)
    elif not payment.paid_at:
        if booking['status'] == 'cancelled':
            if value.get('status') == 'expired':
                payment.status = 'cancelled'
            else:
                money.cancel_payment(session, booking, visit, payment)
        elif value.get('status') == 'expired':
            payment.status = 'expired'
            session.execute(update(Booking).where(Booking.id == booking['id']).values(stripe_payment_intent_id=None))
        elif value.get('status') == 'complete':
            payment.status = 'processing'
        elif payment.status != 'cancel_pending':
            payment.status = 'open'
            url = value.get('url')
            if isinstance(url, str) and url.startswith('https://checkout.stripe.com/'):
                payment.checkout_url = url


def _execute(row, provider):
    # Eligibility is read under the aggregate lock, then the SQL connection is
    # returned to the pool before every provider request.
    with db_session() as session:
        current = session.get(Op, row.id)
        if current.lease_token != row.lease_token:
            raise Deferred('lease_lost', held=True)
        if row.mutation_started_at and row.mutation_started_at < money.now() - timedelta(hours=23) and not row.provider_id:
            raise Deferred('ambiguous_provider_result', held=True)
        if row.kind == 'connect':
            if row.payload['livemode'] != bool(provider.livemode):
                raise RuntimeError('mode_mismatch')
            payment = None
        else:
            payment, booking, visit = _context(session, row)
            _check_mode(payment, provider)
            if row.kind == 'checkout' and (booking['status'] == 'cancelled' or visit.issue_open):
                raise Deferred('visit_on_hold', held=True)
            if row.kind == 'transfer':
                if booking['status'] != 'completed' or not visit.customer_confirmed_at or visit.issue_open or payment.disputed:
                    raise Deferred('visit_on_hold', held=True)
                if not visits.helper_allowed(session, payment.helper_id, visit.service):
                    raise Deferred('helper_ineligible', held=True)
                if not home_stripe.transfer_allowed():
                    raise Deferred('transfers_disabled', held=True)
            if row.kind == 'refund_cancel':
                transfers = session.execute(select(Op).where(Op.payment_id == payment.id, Op.kind == 'transfer',
                    Op.status.in_(('running','succeeded')))).scalars().all()
                reversals = session.execute(select(Op).where(Op.payment_id == payment.id, Op.kind == 'reverse', Op.status == 'succeeded')).scalars().all()
                reversed_ids = {op.payload['transferId'] for op in reversals}
                if any(op.status == 'running' or op.provider_id not in reversed_ids for op in transfers):
                    raise Deferred('reversal_pending')
            if row.kind=='refund_unused' and (visit.issue_open or payment.status=='review_required'
                or row.attempts==1 and not row.provider_id and payment.refunded_cents>0):
                raise Deferred('external_refund_review',held=True)
    operation_id = str(row.id)
    if row.kind == 'checkout':
        _mark_mutation(row)
        return provider.checkout(operation_id, row.payload)
    if row.kind == 'expire':
        return provider.expire(operation_id, row.payload)
    if row.kind.startswith('refund_'):
        if not row.provider_id:
            _mark_mutation(row)
        value = provider.refund_status(row.provider_id) if row.provider_id else provider.refund(operation_id, row.payload)
        return {**dict(value), '_verified_checkout': provider.payment(payment.checkout_id)}
    if row.kind == 'connect':
        _mark_mutation(row)
        return provider.connect(operation_id, row.payload)
    if row.kind == 'reverse':
        _mark_mutation(row)
        return provider.reverse(operation_id, row.payload)
    if row.kind == 'transfer':
        account = provider.account(row.payload['destination'])
        capabilities = account.get('capabilities') or {}
        if account.get('id') != row.payload['destination'] or _metadata(account).get('home_helper_id') != payment.helper_id:
            raise Deferred('account_binding_mismatch', held=True)
        if not account.get('payouts_enabled') or not account.get('details_submitted') or capabilities.get('transfers') != 'active':
            raise Deferred('bank_requirements_due', held=True)
        state = provider.payment(payment.checkout_id)
        _validate_session(payment, state)
        charge = ((state.get('payment_intent') or {}).get('latest_charge') or {})
        balance = charge.get('balance_transaction') or {}
        if charge.get('disputed') or charge.get('id') != row.payload['chargeId']:
            raise Deferred('charge_on_hold', held=True)
        if not isinstance(balance, dict) or balance.get('status') != 'available':
            raise Deferred('funds_pending')
        if charge.get('amount', 0) - charge.get('amount_refunded', 0) < row.payload['amountCents']:
            raise Deferred('insufficient_source', held=True)
        _mark_mutation(row)
        return provider.transfer(operation_id, row.payload)
    raise RuntimeError('unknown_operation')


def _mark_mutation(row):
    # Record possible external mutation before I/O. Read-only fund/bank probes
    # must not start the provider idempotency clock while funds settle for days.
    with db_session() as session:
        current=session.get(Op,row.id,with_for_update=True)
        if current.lease_token!=row.lease_token:
            raise Deferred('lease_lost',held=True)
        if current.mutation_started_at is None:
            current.mutation_started_at=money.now()


def _apply(session, row, value):
    if row.payment_id:
        payment, booking, visit = _context(session, row)
    current = session.get(Op, row.id, with_for_update=True)
    if current.lease_token != row.lease_token:
        return
    if row.kind == 'connect':
        if (_metadata(value).get('home_operation_id') != str(row.id)
            or _metadata(value).get('home_helper_id') != row.payload['helperId']
            or _metadata(value).get('cookcredit_product') != home_stripe.PRODUCT):
            raise RuntimeError('account_binding_mismatch')
        session.execute(update(CookProfile).where(CookProfile.user_id == row.payload['helperId'],
            CookProfile.stripe_account_id.is_(None)).values(stripe_account_id=value['id'], stripe_onboarded=False))
    else:
        if row.kind in ('checkout','expire'):
            _sync_payment(session, payment, booking, visit, value)
        else:
            if _metadata(value).get('home_operation_id') != str(row.id):
                raise RuntimeError('operation_binding_mismatch')
            if value.get('amount') != row.payload['amountCents']:
                raise RuntimeError('amount_mismatch')
            if row.kind.startswith('refund_'):
                _sync_payment(session, payment, booking, visit, value['_verified_checkout'])
                if value.get('status') != 'succeeded':
                    current.provider_id = value['id']
                    current.status = 'review_required' if value.get('status') in ('failed','canceled') else 'retry'
                    current.last_error = 'refund_' + str(value.get('status'))
                    current.available_at = money.now() + timedelta(minutes=2)
                    current.lease_token = current.lease_until = None
                    return
                # Count this exact refund once. Never infer paid/refunded from a
                # checkout return or use a retry to create another provider refund.
                known = session.execute(select(Op).where(Op.payment_id == payment.id,
                    Op.kind.in_(('refund_unused','refund_cancel')), Op.status == 'succeeded')).scalars().all()
                confirmed = sum(op.payload['amountCents'] for op in known) + row.payload['amountCents']
                payment.refunded_cents = max(payment.refunded_cents, confirmed)
                if payment.refunded_cents > payment.amount_cents:
                    raise RuntimeError('refund_overflow')
                payment.status = 'refunded' if payment.refunded_cents == payment.amount_cents else 'paid'
                _bump(session, booking, visit, 'refund_verified', payment)
            if row.kind == 'transfer':
                _bump(session, booking, visit, 'helper_funds_transferred', payment)
            if row.kind == 'reverse':
                _bump(session, booking, visit, 'helper_transfer_reversed', payment)
    current.provider_id, current.status = value['id'], 'succeeded'
    current.lease_token = current.lease_until = current.last_error = None
    session.flush()
    if row.payment_id:
        if row.kind == 'transfer' and (visit.issue_open or payment.disputed or booking['status'] == 'cancelled'):
            money.reverse_transfer(session, payment, current)
        money.ensure_settlement(session, booking, visit)


def _failure(model, row, error):
    with db_session() as session:
        current = session.get(model, row.id, with_for_update=True)
        if not current or current.lease_token != row.lease_token:
            return
        code = error.code if isinstance(error, Deferred) else type(error).__name__
        held = isinstance(error, Deferred) and error.held
        current.status = ('review_required' if code == 'ambiguous_provider_result' else 'held') if held and model is Op else (
            'review_required' if current.attempts >= 24 else 'retry')
        current.last_error, current.lease_token, current.lease_until = code, None, None
        current.available_at = money.now() + timedelta(seconds=min(3600, 30 * 2 ** min(current.attempts, 7)))
        # Definite "not ready" has no mutation ambiguity and can wait for funds.
        if isinstance(error, Deferred) and not held:
            current.attempts = max(0, current.attempts - 1)
            current.status = 'retry'
        emit_event('home_financial_deferred' if isinstance(error, Deferred) else 'home_financial_failed',
            severity='WARNING' if isinstance(error, Deferred) else 'ERROR', kind=row.kind, code=code)


def dispatch_operations(provider=None, limit=5):
    provider = provider or home_stripe.StripeHome()
    counts = {'processed': 0, 'deferred': 0}
    for _ in range(max(1, min(5, int(limit)))):
        row = _claim(Op)
        if not row:
            break
        try:
            value = _execute(row, provider)
            with db_session() as session:
                _apply(session, row, value)
            counts['processed'] += 1
        except Exception as error:
            _failure(Op, row, error)
            counts['deferred'] += 1
    return counts


def receive_event(session, event):
    if bool(event.get('livemode')) != (home_stripe.mode() == 'live'):
        visits.fail('mode_mismatch', 'Webhook mode does not match Home.', 400)
    obj = ((event.get('data') or {}).get('object') or {})
    meta = _metadata(obj)
    payment = None
    if meta.get('cookcredit_product') == home_stripe.PRODUCT:
        try:
            payment = session.get(HomePayment, uuid.UUID(meta.get('home_payment_id', '')))
        except (ValueError, TypeError):
            pass
    if payment is None:
        reference = obj.get('payment_intent')
        reference = reference.get('id') if isinstance(reference, dict) else reference
        if reference:
            payment = session.execute(select(HomePayment).where(HomePayment.payment_intent_id == reference)).scalar_one_or_none()
    if payment is None:
        return {'accepted': True, 'ignored': True}
    session.execute(insert(HomeStripeEvent).values(id=event['id'], kind=event['type'], object_id=obj['id'],
        payment_id=payment.id, livemode=payment.livemode, status='pending').on_conflict_do_nothing())
    session.info['home_dispatch_due'] = money.now()
    return {'accepted': True}


def dispatch_events(provider=None, limit=5):
    provider = provider or home_stripe.StripeHome()
    counts = {'processed': 0, 'deferred': 0}
    for _ in range(max(1, min(5, int(limit)))):
        row = _claim(HomeStripeEvent)
        if not row:
            break
        try:
            with db_session() as session:
                payment = session.get(HomePayment, row.payment_id)
                _check_mode(payment, provider)
                checkout = payment.checkout_id or (row.object_id if row.kind.startswith('checkout.session.') else None)
            if not checkout:
                raise Deferred('checkout_pending')
            value = provider.payment(checkout)
            with db_session() as session:
                payment, booking, visit = _context(session, row)
                current = session.get(HomeStripeEvent, row.id, with_for_update=True)
                if current.lease_token != row.lease_token:
                    continue
                _sync_payment(session, payment, booking, visit, value)
                current.status, current.lease_token, current.lease_until = 'processed', None, None
            counts['processed'] += 1
        except Exception as error:
            _failure(HomeStripeEvent, row, error)
            counts['deferred'] += 1
    return counts
