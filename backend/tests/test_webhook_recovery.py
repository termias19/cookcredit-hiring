"""Durable webhook retries in isolated PostgreSQL; no outbound network."""
import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_report_playback_binding import db
from models import PartnerWebhook, PartnerWebhookDelivery
from services import database, partner_integrations as hooks

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='dedicated local DB required')


@pytest.fixture
def delivery(db, monkeypatch):
    engine = database.SessionLocal.kw['bind']
    PartnerWebhook.__table__.create(engine)
    PartnerWebhookDelivery.__table__.create(engine)
    monkeypatch.setattr(hooks, 'decrypt_webhook_secret', lambda value:'synthetic-test-secret')
    with database.db_session() as session:
        hook = PartnerWebhook(org_id=db.org, url='https://receiver.example.test/events',
                              event_types=['assessment.completed'], secret_ciphertext='test-only')
        session.add(hook)
        session.flush()
        event = hooks.emit_partner_event(session, org_id=db.org, event_type='assessment.completed',
                                        data={'environment':'live', 'status':'review-required'})
        session.flush()
        row = session.query(PartnerWebhookDelivery).one()
        return row.id, hook.id, event


def test_repeated_worker_crash_stops_at_delivery_budget(delivery):
    with database.db_session() as session:
        row = session.get(PartnerWebhookDelivery, delivery[0])
        row.status = 'delivering'
        row.attempts = hooks.MAX_DELIVERY_ATTEMPTS
        row.lock_token = uuid.uuid4()
        row.locked_until = datetime.now(timezone.utc)-timedelta(seconds=1)
    sender = Mock(return_value=SimpleNamespace(status_code=200))
    hooks.dispatch_partner_webhooks(send=sender)
    sender.assert_not_called()
    with database.db_session() as session:
        row = session.get(PartnerWebhookDelivery, delivery[0])
        assert row.status == 'failed'
        assert row.attempts == hooks.MAX_DELIVERY_ATTEMPTS
        assert row.lock_token is None and row.locked_until is None


def test_failed_delivery_retries_identical_signed_event_then_stops(delivery):
    requests = []
    def send(url, **kwargs):
        requests.append(kwargs)
        return SimpleNamespace(status_code=503 if len(requests)==1 else 204)
    assert hooks.dispatch_partner_webhooks(send=send)['retrying'] == 1
    assert hooks.dispatch_partner_webhooks(send=send)['claimed'] == 0
    with database.db_session() as session:
        row = session.get(PartnerWebhookDelivery, delivery[0])
        row.next_attempt_at = datetime.now(timezone.utc)-timedelta(seconds=1)
    assert hooks.dispatch_partner_webhooks(send=send)['delivered'] == 1
    assert hooks.dispatch_partner_webhooks(send=send)['claimed'] == 0
    assert len(requests) == 2
    assert requests[0]['data'] == requests[1]['data']
    for item in requests:
        event = json.loads(item['data'])
        assert event['id'] == delivery[2]
        signature = item['headers']['CookCredit-Signature']
        timestamp = int(signature.split(',')[0][2:])
        assert signature == hooks._sign('synthetic-test-secret', timestamp, item['data'])
        assert item['allow_redirects'] is False


def test_active_lease_and_disabled_hook_do_not_send(delivery):
    with database.db_session() as session:
        row = session.get(PartnerWebhookDelivery, delivery[0])
        row.status = 'delivering'
        row.lock_token = uuid.uuid4()
        row.locked_until = datetime.now(timezone.utc)+timedelta(minutes=1)
    sender = Mock()
    assert hooks.dispatch_partner_webhooks(send=sender)['claimed'] == 0
    with database.db_session() as session:
        row = session.get(PartnerWebhookDelivery, delivery[0])
        row.locked_until = datetime.now(timezone.utc)-timedelta(seconds=1)
        session.get(PartnerWebhook, delivery[1]).active = False
    assert hooks.dispatch_partner_webhooks(send=sender)['claimed'] == 0
    sender.assert_not_called()
