"""A fast wakeup must never precede, replace, or undo durable delivery storage."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from services import database, webhook_dispatch as dispatch


def test_wakeup_is_coalesced_after_commit_and_connection_release(monkeypatch):
    order = []
    session = SimpleNamespace(info={}, commit=lambda: order.append('commit'),
                              close=lambda: order.append('close'), rollback=Mock())
    monkeypatch.setattr(database, 'get_session', lambda: session)
    monkeypatch.setattr(dispatch, 'enqueue_dispatch', lambda due: order.append(due))
    now = datetime.now(timezone.utc)
    with database.db_session() as current:
        dispatch.request_dispatch(current, now + timedelta(seconds=30))
        dispatch.request_dispatch(current, now)
        dispatch.request_dispatch(current, now + timedelta(seconds=60))
        assert not order
    assert order == ['commit', 'close', now]


def test_rollback_never_sends_a_task(monkeypatch):
    session = SimpleNamespace(info={}, commit=Mock(), close=Mock(), rollback=Mock())
    enqueue = Mock()
    monkeypatch.setattr(database, 'get_session', lambda: session)
    monkeypatch.setattr(dispatch, 'enqueue_dispatch', enqueue)
    with pytest.raises(ValueError):
        with database.db_session() as current:
            dispatch.request_dispatch(current, datetime.now(timezone.utc))
            raise ValueError('transaction failed')
    enqueue.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_enqueue_failure_does_not_turn_committed_work_into_request_failure(monkeypatch, capsys):
    session = SimpleNamespace(info={}, commit=Mock(), close=Mock(), rollback=Mock())
    monkeypatch.setattr(database, 'get_session', lambda: session)
    monkeypatch.setattr(dispatch, 'enqueue_dispatch', Mock(side_effect=RuntimeError('private provider error')))
    with database.db_session() as current:
        dispatch.request_dispatch(current, datetime.now(timezone.utc))
    session.commit.assert_called_once()
    session.rollback.assert_not_called()
    output = capsys.readouterr().out
    assert 'webhook_enqueue_failed' in output
    assert 'private provider error' not in output


def test_task_has_bounded_io_oidc_and_no_applicant_data(monkeypatch):
    queue = 'projects/cookcredit-scoring/locations/us-central1/queues/hiring-webhooks'
    origin = 'https://hiring-api.example.test'
    for key, value in {'WEBHOOK_TASKS_QUEUE': queue,
        'WEBHOOK_TASKS_TARGET': origin + '/api/partner/internal/dispatch-webhooks',
        'TASKS_OIDC_SA': 'worker@example.test', 'TASKS_OIDC_AUDIENCE': origin}.items():
        monkeypatch.setenv(key, value)
    client = Mock()
    monkeypatch.setattr(dispatch, '_client', lambda: client)
    assert dispatch.enqueue_dispatch(datetime.now(timezone.utc))
    args = client.create_task.call_args.kwargs
    assert args['timeout'] == 2 and args['retry'] is None
    task = args['request']['task']
    assert task['http_request']['body'] == b'{"limit":10}'
    assert task['http_request']['oidc_token']['audience'] == origin
    assert 'X-Internal-Secret' not in task['http_request']['headers']
    monkeypatch.setenv('WEBHOOK_TASKS_TARGET', 'https://other.example.test/api/partner/internal/dispatch-webhooks')
    with pytest.raises(RuntimeError):
        dispatch.enqueue_dispatch(datetime.now(timezone.utc))
    assert client.create_task.call_count == 1


def test_scheduler_only_configuration_never_creates_cloud_client(monkeypatch):
    monkeypatch.delenv('WEBHOOK_TASKS_QUEUE', raising=False)
    monkeypatch.delenv('WEBHOOK_TASKS_TARGET', raising=False)
    client = Mock()
    monkeypatch.setattr(dispatch, '_client', client)
    assert dispatch.enqueue_dispatch(datetime.now(timezone.utc)) is False
    client.assert_not_called()


def test_dispatch_endpoint_requires_internal_auth_and_bounds_batch(monkeypatch):
    from flask import Flask
    from routes import partner
    from services import operations
    app = Flask(__name__)
    app.register_blueprint(partner.partner_bp)
    worker = Mock(return_value={'claimed': 0, 'delivered': 0, 'retrying': 0, 'failed': 0})
    monkeypatch.setattr(partner, 'dispatch_partner_webhooks', worker)
    monkeypatch.setattr(operations, 'report_queue_health', lambda *_: True)
    monkeypatch.setattr(partner, 'internal_request_authorized', lambda _: False)
    client = app.test_client()
    assert client.post('/internal/dispatch-webhooks', json={'limit': 10}).status_code == 403
    worker.assert_not_called()
    monkeypatch.setattr(partner, 'internal_request_authorized', lambda _: True)
    for invalid in (0, 51, True, '10'):
        assert client.post('/internal/dispatch-webhooks', json={'limit': invalid}).status_code == 400
    assert client.post('/internal/dispatch-webhooks', json={'limit': 10}).status_code == 200
    worker.assert_called_once_with(limit=10)
