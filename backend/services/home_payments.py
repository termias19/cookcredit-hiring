"""Durable Home payment lifecycle. All network I/O belongs to home_finance_worker.

Approved maximum -> verified charge -> completed service -> reconciled expenses
-> unused-allowance refund -> transfer to the helper's Stripe balance. A transfer
is never represented as a completed bank payout. Returns/clicks cannot mark paid.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from models import Booking, CookProfile, User
from models.home_service import (HomeVisit, HomePayment, HomeFinancialOperation,
    HomeQuoteApproval, HomeQuoteHelperAcceptance, HomeMaterialReconciliation)
from services import home_visits as visits, home_quotes as quotes, home_stripe

SYSTEM = 'system:home'
TERMINAL_UNPAID = ('expired', 'cancelled')


def now():
    return datetime.now(timezone.utc)


def operation(session, *, payment, actor, kind, payload, suffix=''):
    key = f'{kind}:{payment.id if payment else actor}:{suffix}'
    existing = session.execute(select(HomeFinancialOperation).where(HomeFinancialOperation.dedupe_key == key)).scalar_one_or_none()
    if existing:
        return existing
    row = HomeFinancialOperation(id=uuid.uuid4(), booking_id=payment.booking_id if payment else None,
        payment_id=payment.id if payment else None, actor_id=actor, kind=kind,
        dedupe_key=key, payload=payload)
    session.add(row)
    session.flush()
    session.info['home_dispatch_due'] = now()
    return row


def payment_for_visit(session, booking_id):
    return session.execute(select(HomePayment).where(HomePayment.booking_id == booking_id)
        .order_by(HomePayment.created_at.desc()).limit(1)).scalar_one_or_none()


def require_payment_access(session, principal, booking_id, operator, lock=False):
    booking, visit = visits.load_visit(session, booking_id, principal['uid'], operator, lock=lock)
    return booking, visit, payment_for_visit(session, booking['id'])


def prepare_checkout(session, principal, booking_id, body, operator):
    visits.strict_object(body, ('version', 'quoteId', 'digest'))
    if not home_stripe.checkout_allowed():
        visits.fail('payments_disabled', 'Online payment is not available yet.', 503)
    booking, visit = quotes.load_locked(session, principal, booking_id, body, operator)
    if booking['eater_id'] != principal['uid']:
        visits.fail('forbidden', 'Only the customer can open checkout.', 403)
    if booking['status'] != 'accepted' or visit.issue_open:
        visits.fail('payment_not_ready', 'Resolve this visit before opening checkout.', 409)
    quote = quotes.current_quote(session, booking, visit, body['quoteId'])
    approval, helper_acceptance = session.get(HomeQuoteApproval, quote.id), session.get(HomeQuoteHelperAcceptance, quote.id)
    if (not approval or not helper_acceptance or body['digest'] != quote.digest
        or approval.digest != quote.digest or helper_acceptance.digest != quote.digest):
        visits.fail('approval_required', 'Review and approve the current itemized quote first.', 409)
    if not visits.helper_allowed(session, booking['cook_id'], visit.service, lock=True):
        visits.fail('helper_ineligible', 'CookCredit must review the helper assignment.', 409)
    remaining = (quote.expires_at - now()).total_seconds()
    if remaining < 1801:
        visits.fail('quote_expiring', 'This quote is expiring. Ask CookCredit for an updated offer.', 409)
    payment = session.execute(select(HomePayment).where(HomePayment.quote_id == quote.id)).scalar_one_or_none()
    if payment and payment.status not in TERMINAL_UNPAID:
        return {'paymentId': str(payment.id), 'version': visit.version}
    live = home_stripe.mode() == 'live'
    if payment:
        if payment.livemode != live or payment.paid_at:
            visits.fail('payment_review_required', 'CookCredit must review the previous payment.', 409)
        payment.checkout_attempt += 1
        payment.status, payment.checkout_id, payment.checkout_url = 'creating', None, None
    else:
        payment = HomePayment(id=uuid.uuid4(), booking_id=booking['id'], quote_id=quote.id,
            customer_id=principal['uid'], helper_id=booking['cook_id'], livemode=live,
            amount_cents=quote.snapshot['maximumTotalCents'], status='creating', checkout_attempt=1)
        session.add(payment)
        session.flush()
    expires = min(int(quote.expires_at.timestamp()), int((now() + timedelta(hours=23)).timestamp()))
    operation(session, payment=payment, actor=principal['uid'], kind='checkout', suffix=str(payment.checkout_attempt),
        payload={'paymentId': str(payment.id), 'quoteId': str(quote.id), 'bookingId': str(booking['id']),
            'amountCents': payment.amount_cents, 'email': principal['email'], 'expiresAt': expires,
            'attempt': payment.checkout_attempt, 'livemode': live})
    visit.version += 1
    visits.event(session, principal['uid'], 'checkout_requested', booking['id'], visit.version, paymentId=str(payment.id))
    return {'paymentId': str(payment.id), 'version': visit.version}


def dto(session, booking, visit, payment, uid, operator):
    if not payment:
        return {'status': 'unpaid', 'checkoutAvailable': home_stripe.checkout_allowed()}
    ops = session.execute(select(HomeFinancialOperation).where(HomeFinancialOperation.payment_id == payment.id)).scalars().all()
    result = {'id': str(payment.id), 'quoteId': str(payment.quote_id), 'status': payment.status,
        'amountCents': payment.amount_cents, 'refundedCents': payment.refunded_cents,
        'issueOpen': visit.issue_open or payment.disputed, 'livemode': payment.livemode,
        'paidAt': payment.paid_at.isoformat() if payment.paid_at else None,
        'operations': [{'kind': op.kind, 'status': op.status} for op in ops],
        'bankPayoutConfirmed': False}
    if uid == booking['eater_id'] and booking['status'] != 'cancelled' and payment.status == 'open':
        result['checkoutUrl'] = payment.checkout_url
    transfers = [op for op in ops if op.kind == 'transfer']
    reversals = [op for op in ops if op.kind == 'reverse']
    reversed_ids = {op.payload['transferId'] for op in reversals if op.status == 'succeeded'}
    outstanding = sum(op.payload['amountCents'] for op in transfers
        if op.status == 'succeeded' and op.provider_id not in reversed_ids)
    result['helperTransferredCents'] = outstanding
    result['helperFunds'] = ('reversal_pending' if any(op.status != 'succeeded' for op in reversals)
        else 'transferred_to_stripe' if outstanding else 'held_after_reversal' if reversed_ids else 'not_released')
    return result


def cancel_payment(session, booking, visit, payment):
    if not payment:
        return
    if payment.paid_at and payment.refunded_cents == payment.amount_cents:
        payment.status = 'refunded'
        return
    payment.status = 'cancel_pending'
    if payment.checkout_id:
        operation(session, payment=payment, actor=SYSTEM, kind='expire', suffix=payment.checkout_id,
            payload={'checkoutId': payment.checkout_id})
    if payment.paid_at and payment.amount_cents > payment.refunded_cents:
        transfer = session.execute(select(HomeFinancialOperation).where(
            HomeFinancialOperation.payment_id == payment.id, HomeFinancialOperation.kind == 'transfer')).scalar_one_or_none()
        if transfer and transfer.status == 'succeeded':
            reverse_transfer(session, payment, transfer)
        operation(session, payment=payment, actor=SYSTEM, kind='refund_cancel',
            payload={'paymentIntentId': payment.payment_intent_id, 'paymentId': str(payment.id),
                'amountCents': payment.amount_cents - payment.refunded_cents})


def reverse_transfer(session, payment, transfer):
    if transfer.provider_id:
        operation(session, payment=payment, actor=SYSTEM, kind='reverse', suffix=transfer.provider_id,
            payload={'transferId': transfer.provider_id, 'amountCents': transfer.payload['amountCents'],
                     'paymentId': str(payment.id)})


def ensure_settlement(session, booking, visit):
    payment = payment_for_visit(session, booking['id'])
    if not payment or not payment.paid_at or payment.disputed or visit.issue_open:
        return
    if booking['status'] == 'cancelled':
        cancel_payment(session, booking, visit, payment)
        return
    if booking['status'] != 'completed' or not visit.customer_confirmed_at:
        return
    quote = quotes.current_quote(session, booking, visit, str(payment.quote_id))
    reconciled = session.get(HomeMaterialReconciliation, quote.id)
    if not reconciled and quote.snapshot['materialsCapCents'] == 0:
        # No new expenses: retain the original reviewed fixed tax and labor.
        # This is derivation from the approved quote, not a new human receipt review.
        s = quote.snapshot
        reconciled = HomeMaterialReconciliation(quote_id=quote.id, booking_id=booking['id'],
            reviewed_by=quote.created_by, snapshot={'basis': 'fixed_quote_no_materials',
                'materialsActualCents': 0, 'taxActualCents': s['taxCapCents'],
                'customerFinalCents': s['maximumTotalCents'], 'unusedAllowanceCents': 0,
                'helperActualPayCents': s['helperLaborNetCents']})
        session.add(reconciled)
        session.flush()
    if not reconciled:
        return
    unused = reconciled.snapshot['unusedAllowanceCents']
    if payment.refunded_cents > unused:
        return  # A dispute/manual adjustment needs an explicit operator review.
    if unused:
        refund = operation(session, payment=payment, actor=SYSTEM, kind='refund_unused',
            payload={'paymentIntentId': payment.payment_intent_id, 'paymentId': str(payment.id), 'amountCents': unused})
        if refund.status != 'succeeded' or payment.refunded_cents != unused:
            return
    account_id = session.execute(select(CookProfile.stripe_account_id).where(CookProfile.user_id == payment.helper_id)).scalar()
    if not account_id or not payment.charge_id:
        return
    transfers = session.execute(select(HomeFinancialOperation).where(HomeFinancialOperation.payment_id == payment.id,
        HomeFinancialOperation.kind == 'transfer').order_by(HomeFinancialOperation.created_at)).scalars().all()
    reversals = session.execute(select(HomeFinancialOperation).where(HomeFinancialOperation.payment_id == payment.id,
        HomeFinancialOperation.kind == 'reverse', HomeFinancialOperation.status == 'succeeded')).scalars().all()
    reversed_ids = {row.payload['transferId'] for row in reversals}
    if any(row.status in ('pending','running','retry','held','review_required') for row in transfers):
        return
    outstanding = sum(row.payload['amountCents'] for row in transfers
        if row.status == 'succeeded' and row.provider_id not in reversed_ids)
    target = reconciled.snapshot['helperActualPayCents']
    if outstanding >= target:
        return
    operation(session, payment=payment, actor=SYSTEM, kind='transfer', suffix=str(len(transfers)),
        payload={'paymentId': str(payment.id), 'destination': account_id, 'chargeId': payment.charge_id,
                 'amountCents': target - outstanding})


def on_visit_change(session, booking, visit, action):
    if action not in ('cancel', 'report_issue', 'confirm', 'resolve_issue'):
        return
    payment = payment_for_visit(session, booking['id'])
    if action == 'cancel':
        cancel_payment(session, booking, visit, payment)
    elif action == 'report_issue' and payment:
        transfer = session.execute(select(HomeFinancialOperation).where(HomeFinancialOperation.payment_id == payment.id,
            HomeFinancialOperation.kind == 'transfer', HomeFinancialOperation.status == 'succeeded')).scalar_one_or_none()
        if transfer:
            reverse_transfer(session, payment, transfer)
    elif action in ('confirm', 'resolve_issue'):
        if action == 'resolve_issue' and payment and payment.paid_at and booking['status'] == 'accepted' and not payment.disputed:
            booking['status'] = 'confirmed'
            session.execute(update(Booking).where(Booking.id == booking['id']).values(status='confirmed'))
        ensure_settlement(session, booking, visit)


def service_action(session, principal, booking, visit, action):
    uid, stamp, changes = principal['uid'], now(), {}
    if action in ('start', 'finish') and uid != booking['cook_id']:
        visits.fail('forbidden', 'Only the assigned helper can update this work.', 403)
    if action == 'confirm' and uid != booking['eater_id']:
        visits.fail('forbidden', 'Only the customer can confirm completion.', 403)
    payment = payment_for_visit(session, booking['id'])
    if not payment or payment.status != 'paid' or not payment.paid_at or payment.disputed:
        visits.fail('payment_required', 'Verified payment is required before the service can progress.', 409)
    if action == 'start':
        if booking['status'] != 'confirmed' or not visits.helper_allowed(session, uid, visit.service, lock=True):
            visits.fail('work_not_ready', 'This visit is not ready to start.', 409)
        changes.update(status='in_progress', started_at=stamp)
    elif action == 'finish':
        if booking['status'] != 'in_progress':
            visits.fail('work_not_ready', 'Start the agreed visit before finishing it.', 409)
        changes.update(status='pending_confirmation', completed_at=stamp)
    elif action == 'confirm':
        if booking['status'] != 'pending_confirmation':
            visits.fail('work_not_ready', 'The helper must finish before you confirm.', 409)
        changes['status'] = 'completed'
        visit.customer_confirmed_at = stamp
    return changes


def refresh_payment(session, principal, booking_id, operator):
    from models.home_service import HomeStripeEvent
    booking, visit, payment = require_payment_access(session, principal, booking_id, operator, lock=True)
    if not payment or not payment.checkout_id:
        return {'queued': False}
    window = int(now().timestamp()) // 15
    session.execute(insert(HomeStripeEvent).values(id=f'refresh:{payment.id}:{window}', kind='refresh',
        object_id=payment.checkout_id, payment_id=payment.id, livemode=payment.livemode,
        status='pending').on_conflict_do_nothing())
    session.info['home_dispatch_due'] = now()
    return {'queued': True}
