"""Real SQL lifecycle with a deterministic provider; never calls live Stripe."""
import copy
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from models import Booking, CookProfile
from models.home_service import HomeVisit, HomePayment, HomeFinancialOperation as Op, HomeStripeEvent
from services import database, home_payments as money, home_stripe, home_finance_worker as worker
from tests.test_home_quotes import (app, home_db, headers, post, fully_approved, detail,
    reconciliation_body, change)


class FakeStripe:
    livemode = False

    def __init__(self):
        self.sessions, self.results, self.calls = {}, {}, []
        self.account_ready, self.funds_ready = True, True
        self.on_transfer = None
        self.fail_after_checkout = False

    def checkout(self, operation, payload):
        if operation not in self.results:
            self.calls.append(('checkout', operation))
            meta = {'cookcredit_product': 'home_services', 'home_operation_id': operation,
                'home_payment_id': payload['paymentId'], 'home_quote_id': payload['quoteId'],
                'home_checkout_attempt': str(payload['attempt'])}
            value = {'id': 'cs_' + uuid.uuid4().hex, 'mode': 'payment', 'livemode': False,
                'currency': 'usd', 'amount_total': payload['amountCents'], 'metadata': meta,
                'status': 'open', 'payment_status': 'unpaid', 'payment_intent': None,
                'url': 'https://checkout.stripe.com/c/pay/synthetic'}
            self.results[operation] = value
            self.sessions[value['id']] = value
            if self.fail_after_checkout:
                raise TimeoutError('synthetic lost response')
        return copy.deepcopy(self.results[operation])

    def payment(self, identifier):
        return copy.deepcopy(self.sessions[identifier])

    def pay(self, identifier):
        value = self.sessions[identifier]
        intent = 'pi_' + uuid.uuid4().hex
        value.update(status='complete', payment_status='paid', payment_intent={
            'id': intent, 'amount': value['amount_total'], 'currency': 'usd', 'livemode': False,
            'metadata': value['metadata'], 'status': 'succeeded', 'latest_charge': {
                'id': 'ch_' + uuid.uuid4().hex, 'payment_intent': intent, 'paid': True,
                'amount': value['amount_total'], 'amount_refunded': 0, 'currency': 'usd', 'livemode': False,
                'balance_transaction': {'status': 'available' if self.funds_ready else 'pending'}, 'disputed': False}})

    def refund(self, operation, payload):
        if operation not in self.results:
            self.calls.append(('refund', operation))
            value = {'id': 're_' + uuid.uuid4().hex, 'status': 'succeeded', 'amount': payload['amountCents'],
                     'metadata': {'home_operation_id': operation}}
            self.results[operation] = value
            for session in self.sessions.values():
                intent = session.get('payment_intent')
                if isinstance(intent, dict) and intent['id'] == payload['paymentIntentId']:
                    intent['latest_charge']['amount_refunded'] += payload['amountCents']
        return copy.deepcopy(self.results[operation])

    def refund_status(self, identifier):
        return next(copy.deepcopy(value) for value in self.results.values() if value['id'] == identifier)

    def expire(self, operation, payload):
        value = self.sessions[payload['checkoutId']]
        if value['status'] == 'open':
            value['status'] = 'expired'
        return copy.deepcopy(value)

    def account(self, identifier):
        return {'id': identifier, 'payouts_enabled': self.account_ready, 'details_submitted': self.account_ready,
                'capabilities': {'transfers': 'active'}, 'metadata': {'home_helper_id': 'helper'}}

    def transfer(self, operation, payload):
        if operation not in self.results:
            if self.on_transfer:
                self.on_transfer()
            self.calls.append(('transfer', operation))
            self.results[operation] = {'id': 'tr_' + uuid.uuid4().hex, 'amount': payload['amountCents'],
                                     'metadata': {'home_operation_id': operation}}
        return copy.deepcopy(self.results[operation])

    def reverse(self, operation, payload):
        if operation not in self.results:
            self.calls.append(('reverse', operation))
            self.results[operation] = {'id': 'trr_' + uuid.uuid4().hex, 'amount': payload['amountCents'],
                                     'metadata': {'home_operation_id': operation}}
        return copy.deepcopy(self.results[operation])


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('HOME_PAYMENT_MODE', 'test')
    monkeypatch.setenv('HOME_CHECKOUT_ENABLED', '1')
    monkeypatch.setenv('HOME_TRANSFERS_ENABLED', '1')
    monkeypatch.setenv('HOME_STRIPE_WEBHOOK_SECRET', 'synthetic-home-signing-fixture')
    return FakeStripe()


def fresh(client, row):
    value = detail(client, row)
    return {'id': value['id'], 'version': value['version'], 'status': value['status'], 'quoteId': value['quoteId']}


def checkout(client, row, provider):
    quote = detail(client, row)['quote']
    response = post(client, f"/visits/{row['id']}/checkout", {'version': row['version'],
        'quoteId': quote['id'], 'digest': quote['digest']}, 'customer')
    assert response.status_code == 202, response.json
    assert worker.dispatch_operations(provider)['processed'] == 1
    with database.db_session() as session:
        payment = session.get(HomePayment, uuid.UUID(response.json['paymentId']))
        return payment.id, payment.checkout_id


def notify(client, provider, checkout_id, *, event_id=None):
    value = provider.payment(checkout_id)
    event = {'id': event_id or 'evt_' + uuid.uuid4().hex, 'type': 'checkout.session.completed',
             'livemode': False, 'data': {'object': value}}
    raw = json.dumps(event).encode()
    stamp = int(time.time())
    digest = hmac.new(b'synthetic-home-signing-fixture', str(stamp).encode() + b'.' + raw, hashlib.sha256).hexdigest()
    result = client.post('/api/home/stripe/webhook', data=raw, content_type='application/json',
        headers={'Stripe-Signature': f't={stamp},v1={digest}'})
    assert result.status_code == 200, result.json
    return event


def paid(client, provider):
    row, _ = fully_approved(client)
    payment, checkout_id = checkout(client, row, provider)
    provider.pay(checkout_id)
    notify(client, provider, checkout_id)
    assert worker.dispatch_events(provider)['processed'] == 1
    return fresh(client, row), payment, checkout_id


def completed(client, provider):
    row, payment, checkout_id = paid(client, provider)
    with database.db_session() as session:
        session.execute(update(CookProfile).where(CookProfile.user_id == 'helper').values(stripe_account_id='acct_synthetic'))
    row = change(client, row, 'start', uid='helper').json
    row = change(client, row, 'finish', uid='helper').json
    row = change(client, row, 'confirm', uid='customer').json
    result = post(client, f"/visits/{row['id']}/materials/reconcile", reconciliation_body(client, row))
    assert result.status_code == 200, result.json
    return fresh(client, row), payment, checkout_id


def test_signed_webhook_canonical_payment_and_full_settlement(app, provider):
    client = app.test_client()
    row, payment, checkout_id = completed(client, provider)
    before = detail(client, row)['payment']
    assert before['status'] == 'paid' and before['helperFunds'] == 'not_released'
    assert worker.dispatch_operations(provider)['processed'] >= 2  # refund then transfer
    value = detail(client, row)['payment']
    assert value['refundedCents'] == 277 and value['helperFunds'] == 'transferred_to_stripe'
    assert value['bankPayoutConfirmed'] is False
    assert [kind for kind, _ in provider.calls].count('refund') == 1
    assert [kind for kind, _ in provider.calls].count('transfer') == 1
    for _ in range(3):
        notify(client, provider, checkout_id, event_id='evt_duplicate')
        worker.dispatch_events(provider)
        worker.dispatch_operations(provider)
    assert [kind for kind, _ in provider.calls].count('transfer') == 1


def test_return_url_or_unsigned_payload_cannot_mark_payment_paid(app, provider):
    client = app.test_client()
    row, _ = fully_approved(client)
    payment, checkout_id = checkout(client, row, provider)
    assert client.post('/api/home/stripe/webhook', json={'type':'checkout.session.completed'}).status_code == 400
    value = detail(client, row)
    assert value['payment']['status'] == 'open' and value['status'] == 'accepted'
    assert change(client, fresh(client, row), 'start', uid='helper').status_code == 409
    event = notify(client, provider, checkout_id)
    worker.dispatch_events(provider)
    assert detail(client, row)['payment']['status'] == 'open'


def test_checkout_timeout_reuses_exact_provider_operation(app, provider):
    client = app.test_client()
    row, _ = fully_approved(client)
    quote = detail(client, row)['quote']
    provider.fail_after_checkout = True
    result = post(client, f"/visits/{row['id']}/checkout", {'version': row['version'],
        'quoteId': quote['id'], 'digest': quote['digest']}, 'customer')
    assert result.status_code == 202
    assert worker.dispatch_operations(provider)['deferred'] == 1
    with database.db_session() as session:
        session.execute(update(Op).where(Op.kind == 'checkout').values(available_at=money.now()-timedelta(seconds=1)))
    assert worker.dispatch_operations(provider)['processed'] == 1
    assert [kind for kind, _ in provider.calls].count('checkout') == 1


def test_cancellation_race_refunds_verified_late_payment(app, provider):
    client = app.test_client()
    row, _ = fully_approved(client)
    payment, checkout_id = checkout(client, row, provider)
    cancelled = change(client, fresh(client, row), 'cancel', uid='customer')
    assert cancelled.status_code == 200
    provider.pay(checkout_id)  # a charge completes before expiry dispatch wins
    notify(client, provider, checkout_id)
    worker.dispatch_events(provider)
    worker.dispatch_operations(provider)
    value = detail(client, row)
    assert value['status'] == 'cancelled'
    assert value['payment']['refundedCents'] == value['payment']['amountCents']
    assert value['payment']['status'] == 'refunded'
    assert not any(kind == 'transfer' for kind, _ in provider.calls)


def test_issue_during_external_transfer_queues_reversal(app, provider):
    client = app.test_client()
    row, _, _ = completed(client, provider)
    def report():
        with app.test_client() as other:
            response = change(other, fresh(other, row), 'report_issue', uid='customer')
            assert response.status_code == 200
    provider.on_transfer = report
    worker.dispatch_operations(provider)
    assert [kind for kind, _ in provider.calls].count('reverse') == 1
    assert detail(client, row)['issueOpen']
    assert detail(client, row)['payment']['helperFunds'] == 'held_after_reversal'


def test_unknown_mutation_older_than_provider_idempotency_window_is_held(app, provider):
    client = app.test_client()
    row, _ = fully_approved(client)
    quote = detail(client, row)['quote']
    post(client, f"/visits/{row['id']}/checkout", {'version': row['version'], 'quoteId':quote['id'], 'digest':quote['digest']}, 'customer')
    with database.db_session() as session:
        session.execute(update(Op).values(first_started_at=money.now()-timedelta(hours=24)))
    worker.dispatch_operations(provider)
    with database.db_session() as session:
        op = session.execute(select(Op).where(Op.kind=='checkout')).scalar_one()
        assert op.status == 'review_required' and op.last_error == 'ambiguous_provider_result'
    assert provider.calls == []


def test_financial_operation_payload_is_immutable_in_database(app, provider):
    client = app.test_client()
    row, _ = fully_approved(client)
    checkout(client, row, provider)
    with pytest.raises(DBAPIError):
        with database.db_session() as session:
            session.execute(update(Op).values(payload={'amountCents':1}))


def test_live_key_does_not_enable_checkout_refunds_or_transfers(monkeypatch):
    monkeypatch.setenv('HOME_PAYMENT_MODE','live')
    monkeypatch.delenv('HOME_CHECKOUT_ENABLED',raising=False)
    monkeypatch.delenv('HOME_TRANSFERS_ENABLED',raising=False)
    assert not home_stripe.checkout_allowed() and not home_stripe.transfer_allowed()
    with pytest.raises(RuntimeError,match='refunds disabled'):
        home_stripe.StripeHome().refund('synthetic', {})


def test_internal_worker_and_financial_operations_are_not_public(app):
    client=app.test_client()
    assert client.post('/api/home/internal/dispatch',json={}).status_code==403
    assert client.get('/api/home/operations',headers=headers('customer')).status_code==403
