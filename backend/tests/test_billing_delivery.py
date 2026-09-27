"""Billing inbox and checkout races use only an isolated local PostgreSQL schema."""
import os
import uuid
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock
import pytest
from tests.test_hiring_postgres import db, client, headers
from models import Org, StripeEvent
from models.billing_catalog import HiringPrice
from services import database, webhook_dispatch
from routes import stripe as billing

pytestmark = pytest.mark.skipif(not os.getenv('HIRING_TEST_DATABASE_URL'), reason='local database required')


def event(db):
    return {'id': 'evt_test', 'type': 'customer.subscription.updated', 'livemode': False,
            'data': {'object': {'id': 'sub_hiring', 'customer': 'cus_hiring',
                'metadata': {'cookcredit_org_id': str(db.org), 'cookcredit_product': 'hiring'},
                'status': 'active', 'items': {'data': [{'price': {'id': 'price_team'}}]},
                'customer_email': 'private@example.test'}}}


def test_async_receipt_commits_before_provider_work_and_deduplicates(db, client, monkeypatch):
    monkeypatch.setenv('STRIPE_ASYNC_ENABLED', '1')
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    incoming = event(db)
    monkeypatch.setattr(billing, 'construct_webhook_event', lambda *a: incoming)
    provider = Mock(return_value=incoming['data']['object'])
    monkeypatch.setattr(billing, 'retrieve_billing_subscription', provider)
    wake = Mock(side_effect=RuntimeError('queue outage'))
    monkeypatch.setattr(webhook_dispatch, 'enqueue_dispatch', wake)
    assert client.post('/stripe/webhook', data=b'signed').json['queued'] is True
    assert client.post('/stripe/webhook', data=b'signed').json['duplicate'] is True
    provider.assert_not_called()
    with database.db_session() as session:
        row = session.get(StripeEvent, incoming['id'])
        assert row.processed_at is None and row.attempts == 0
        assert 'customer_email' not in row.payload
        assert session.get(Org, db.org).plan == 'trial'
    assert billing.dispatch_billing_events()['processed'] == 1
    assert billing.dispatch_billing_events()['processed'] == 0
    with database.db_session() as session:
        assert session.get(Org, db.org).plan == 'team'
        assert session.get(StripeEvent, incoming['id']).payload is None
    provider.assert_called_once()


def test_async_failure_rolls_back_entitlement_and_retries(db, client, monkeypatch):
    monkeypatch.setenv('STRIPE_ASYNC_ENABLED', '1')
    incoming = event(db)
    monkeypatch.setattr(billing, 'construct_webhook_event', lambda *a: incoming)
    client.post('/stripe/webhook', data=b'signed')
    def broken(session, *args):
        session.get(Org, db.org).plan = 'integration'
        session.flush()
        raise RuntimeError('provider timeout')
    monkeypatch.setattr(billing, '_process_event', broken)
    assert billing.dispatch_billing_events()['retrying'] == 1
    with database.db_session() as session:
        assert session.get(Org, db.org).plan == 'trial'
        row = session.get(StripeEvent, incoming['id'])
        assert row.attempts == 1 and row.processed_at is None
        row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    monkeypatch.setattr(billing, '_process_event', lambda *a: None)
    assert billing.dispatch_billing_events()['processed'] == 1


def test_concurrent_checkout_requests_share_one_provider_idempotency_key(db, client, monkeypatch):
    with database.db_session() as session:
        row = HiringPrice(plan='team', interval='month', currency='usd', amount=9900,
                          limits={'seats': 5}, state='published', active=True,
                          stripe_price_id='price_team', created_by='owner')
        session.add(row); session.flush(); price_id = str(row.id)
        session.get(Org, db.org).stripe_customer_id = 'cus_hiring'
    barrier = Barrier(2)
    keys = []
    def create(**kwargs):
        keys.append(kwargs['request_id'])
        barrier.wait(timeout=10)
        return {'id': 'cs_same', 'url': 'https://checkout.stripe.test/same'}
    monkeypatch.setattr(billing, 'create_subscription_checkout', create)
    def start(_):
        with client.application.test_client() as browser:
            return browser.post('/stripe/business/checkout', headers=headers('employer'),
                                json={'requestId': str(uuid.uuid4()), 'priceId': price_id}).status_code
    with ThreadPoolExecutor(max_workers=2) as workers:
        assert list(workers.map(start, range(2))) == [201, 201]
    assert len(set(keys)) == 1
    monkeypatch.setattr(billing, 'retrieve_billing_checkout', lambda _: {'id': 'cs_same', 'status': 'open', 'url': 'https://checkout.stripe.test/same'})
    assert start(0) == 200
    assert len(keys) == 2


def test_other_product_events_and_unauthorized_worker_are_ignored(db, client, monkeypatch):
    monkeypatch.setenv('STRIPE_ASYNC_ENABLED', '1')
    incoming = event(db)
    incoming['data']['object']['metadata']['cookcredit_product'] = 'toque'
    monkeypatch.setattr(billing, 'construct_webhook_event', lambda *a: incoming)
    assert client.post('/stripe/webhook', data=b'signed').json['ignored'] is True
    with database.db_session() as session:
        assert session.query(StripeEvent).count() == 0
    assert client.post('/stripe/internal/dispatch-events').status_code == 403


def test_uncertain_checkout_retry_keeps_same_key_beyond_browser_request(db, client, monkeypatch):
    with database.db_session() as session:
        row = HiringPrice(plan='team', interval='month', currency='usd', amount=9900,
                          limits={'seats': 5}, state='published', active=True,
                          stripe_price_id='price_team', created_by='owner')
        session.add(row); session.flush(); price_id = str(row.id)
        session.get(Org, db.org).stripe_customer_id = 'cus_hiring'
    create = Mock(side_effect=[TimeoutError(), {'id': 'cs_recovered', 'url': 'https://checkout.stripe.test/recovered'}])
    monkeypatch.setattr(billing, 'create_subscription_checkout', create)
    def start():
        return client.post('/stripe/business/checkout', headers=headers('employer'),
                           json={'requestId': str(uuid.uuid4()), 'priceId': price_id})
    assert start().status_code == 503
    assert start().status_code == 201
    assert create.call_args_list[0].kwargs['request_id'] == create.call_args_list[1].kwargs['request_id']
    with database.db_session() as session:
        org = session.get(Org, db.org)
        state = dict(org.billing_checkout)
        state.pop('sessionId')
        state['createdAt'] = (datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()
        org.billing_checkout = state
    assert start().status_code == 409
    assert create.call_count == 2


def test_unknown_subscription_price_cannot_replace_workspace_plan(db, client, monkeypatch):
    incoming = event(db)
    incoming['data']['object']['items']['data'][0]['price']['id'] = 'price_other_product'
    monkeypatch.setattr(billing, 'construct_webhook_event', lambda *a: incoming)
    monkeypatch.setattr(billing, 'retrieve_billing_subscription', lambda *_: incoming['data']['object'])
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'integration'
    assert client.post('/stripe/webhook', data=b'signed').status_code == 200
    with database.db_session() as session:
        org = session.get(Org, db.org)
        assert org.plan == 'integration'
        assert org.stripe_subscription_id is None


def test_multiple_workers_apply_one_event_once(db, client, monkeypatch):
    from threading import Event
    monkeypatch.setenv('STRIPE_ASYNC_ENABLED', '1')
    incoming = event(db)
    monkeypatch.setattr(billing, 'construct_webhook_event', lambda *a: incoming)
    assert client.post('/stripe/webhook', data=b'signed').status_code == 200
    entered, release = Event(), Event()
    def process(*_):
        entered.set()
        assert release.wait(10)
    run = Mock(side_effect=process)
    monkeypatch.setattr(billing, '_process_event', run)
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(billing.dispatch_billing_events)
        try:
            assert entered.wait(5)
            assert billing.dispatch_billing_events()['processed'] == 0
        finally:
            release.set()
        assert first.result(timeout=5)['processed'] == 1
    run.assert_called_once()


def test_controlled_billing_rollout_blocks_non_owner_checkout(db, client, monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_OWNER_ONLY', '1')
    provider = Mock()
    monkeypatch.setattr(billing, 'create_subscription_checkout', provider)
    assert client.post('/stripe/business/checkout', headers=headers('employer'), json={}).status_code == 403
    provider.assert_not_called()
