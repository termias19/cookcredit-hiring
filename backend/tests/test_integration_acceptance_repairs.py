import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from tests.test_hiring_postgres import db, client, headers, integration_auth
from models import Org, PartnerWebhookDelivery, StripeEvent
from services import database, operations, webhook_dispatch


def test_replay_wakes_committed_delivery_but_keeps_active_worker_lease(db, client, monkeypatch):
    integration_auth(db, client)
    with database.db_session() as session:
        session.get(Org, db.other_org).plan = 'integration'
    hook = client.post('/partner/manage/webhooks', headers=headers('employer'), json={
        'url': 'https://hooks.example.test/replay', 'eventTypes': ['assessment.invited'],
    }).json['webhook']
    did = uuid.uuid4()
    with database.db_session() as session:
        session.add(PartnerWebhookDelivery(id=did, webhook_id=uuid.UUID(hook['id']),
            event_id=uuid.uuid4(), event_type='assessment.invited', payload={'synthetic': True},
            status='failed', attempts=10, next_attempt_at=datetime.now(timezone.utc)))
    def wake(*args, **kwargs):
        with database.db_session() as session:
            row = session.get(PartnerWebhookDelivery, did)
            assert row.status == 'pending' and row.attempts == 0
    dispatch = Mock(side_effect=wake)
    monkeypatch.setattr(webhook_dispatch, 'enqueue_dispatch', dispatch)
    url = f'/partner/manage/webhook-deliveries/{did}/replay'
    assert client.post(url, headers=headers('other')).status_code == 404
    assert client.post(url, headers=headers('employer')).status_code == 200
    dispatch.assert_called_once()
    token = uuid.uuid4()
    with database.db_session() as session:
        row = session.get(PartnerWebhookDelivery, did)
        row.status = 'delivering'; row.lock_token = token
        row.locked_until = datetime.now(timezone.utc) + timedelta(minutes=1)
    assert client.post(url, headers=headers('employer')).status_code == 409
    dispatch.assert_called_once()
    with database.db_session() as session:
        assert session.get(PartnerWebhookDelivery, did).lock_token == token


def test_billing_monitor_reports_stale_pending_and_terminal_failure(db, capsys):
    now = datetime.now(timezone.utc)
    with database.db_session() as session:
        session.add(StripeEvent(id='evt_stale', event_type='invoice.paid', livemode=False,
            received_at=now-timedelta(minutes=11), processed_at=None, payload={'id':'synthetic'},
            attempts=1, next_attempt_at=now+timedelta(minutes=1)))
        session.flush()
        session.get(StripeEvent, 'evt_stale').processed_at = None
    assert not operations.report_queue_health('billing')
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event['queue'] == 'billing' and event['pending'] == 1 and event['oldestSeconds'] >= 660
    with database.db_session() as session:
        row = session.get(StripeEvent, 'evt_stale'); row.attempts = 24; row.next_attempt_at = None
    assert not operations.report_queue_health('billing')
    event = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert event['failed'] == 1 and event['pending'] == 0
    with database.db_session() as session:
        row = session.get(StripeEvent, 'evt_stale'); row.processed_at = now; row.payload = None
    assert operations.report_queue_health('billing')
