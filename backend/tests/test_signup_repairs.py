from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import os
import pytest
from services import database, account_email, webhook_dispatch
from models.account_email import AccountEmail
from tests.test_report_playback_binding import db


def test_email_wakes_existing_queue_after_commit_and_without_customer_data(monkeypatch):
    now = datetime.now(timezone.utc)
    order = []
    session = SimpleNamespace(info={}, commit=lambda: order.append('commit'), close=lambda: order.append('close'), rollback=Mock())
    monkeypatch.setattr(database, 'get_session', lambda: session)
    monkeypatch.setattr(webhook_dispatch, 'enqueue_dispatch', lambda due, kind: order.append((due, kind)))
    with database.db_session() as current:
        webhook_dispatch.request_dispatch(current, now, kind='email')
    assert order == ['commit', 'close', (now, 'email')]


def test_email_wakeup_reuses_existing_queue_and_authenticated_worker(monkeypatch):
    monkeypatch.delenv('EMAIL_TASKS_QUEUE', raising=False)
    monkeypatch.delenv('EMAIL_TASKS_TARGET', raising=False)
    monkeypatch.setenv('WEBHOOK_TASKS_QUEUE', 'projects/test/locations/region/queues/existing')
    monkeypatch.setenv('TASKS_OIDC_AUDIENCE', 'https://hiring.example.test')
    monkeypatch.setenv('TASKS_OIDC_SA', 'existing@example.test')
    client = Mock()
    monkeypatch.setattr(webhook_dispatch, '_client', lambda: client)
    assert webhook_dispatch.enqueue_dispatch(datetime.now(timezone.utc), kind='email')
    task = client.create_task.call_args.kwargs['request']['task']
    assert task['http_request']['url'] == 'https://hiring.example.test/api/auth/internal/dispatch-emails'
    assert task['http_request']['oidc_token']['audience'] == 'https://hiring.example.test'
    assert task['http_request']['body'] == b'{"limit":10}'


@pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='isolated PostgreSQL required')
def test_verification_resend_uses_rolling_minute_and_serializes_concurrent_clicks(db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    AccountEmail.__table__.create(database.SessionLocal.kw['bind'])
    now = datetime(2026, 9, 28, 0, 4, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(account_email, 'utcnow', lambda: now)
    monkeypatch.setattr(webhook_dispatch, 'enqueue_dispatch', lambda *a, **kw: False)
    def enqueue(_=None):
        with database.db_session() as session:
            return account_email.enqueue_account_email(session, kind='verify', recipient='candidate@example.test', user_id='candidate')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(enqueue, range(4)))
    assert sum(r['queued'] for r in results) == 1
    now += timedelta(seconds=2)
    assert enqueue() == {'queued': False, 'retryAfterSeconds': 58}
    now += timedelta(seconds=58)
    assert enqueue()['queued'] is True
    with database.db_session() as session:
        assert session.query(AccountEmail).count() == 2
