"""HTTP boundary regressions. No real Firebase credentials or storage are used."""
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from flask import Flask
from routes import business, skills
from services import skill_attempts, scoring_client
from middleware import auth


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, '_verify_token', lambda _: {'uid': 'employer', 'email': 'test@example.test'})
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    app.register_blueprint(business.business_bp, url_prefix='/business')
    app.register_blueprint(skills.skills_bp, url_prefix='/skills')
    return app.test_client()


@contextmanager
def fake_session():
    yield SimpleNamespace(get=lambda *a: SimpleNamespace(skill_verified=True, skill_test_video_url='https://legacy.invalid/clip'))


def test_employer_created_pipeline_is_not_video_consent(client, monkeypatch):
    monkeypatch.setattr(business, 'db_session', fake_session)
    monkeypatch.setattr(business, '_org_for', lambda *a: SimpleNamespace(id='org'))
    monkeypatch.setattr(business, '_require_business', lambda *a: True)
    monkeypatch.setattr(business, '_cook_in_org_pipeline', lambda *a: True)
    # New access gate must fail closed even if the legacy relationship exists.
    monkeypatch.setattr(business, '_seat_role', lambda *a: 'viewer')
    response = client.get('/business/candidate/cook/video', headers={'Authorization': 'Bearer test'})
    assert response.status_code == 403
    assert 'videoUrl' not in response.json


def test_retryable_recompute_does_not_ack_success(client, monkeypatch):
    monkeypatch.setenv('INTERNAL_SECRET', 'test-only')
    monkeypatch.setattr(skills, 'run_recompute', lambda _: None)
    response = client.post('/skills/recompute', json={'attempt_id': '00000000-0000-0000-0000-000000000001'}, headers={'X-Internal-Secret': 'test-only'})
    assert response.status_code == 503


def test_queue_outage_never_runs_inline(monkeypatch):
    monkeypatch.setenv('TASKS_QUEUE', 'test-queue')
    monkeypatch.setenv('TASKS_TARGET_URL', 'https://worker.example.test')
    monkeypatch.setattr(skill_attempts, '_enqueue_cloud_task', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('offline')))
    inline = []
    monkeypatch.setattr(skill_attempts, '_run_inline', lambda *a: inline.append(a))
    with pytest.raises(Exception):
        skill_attempts.enqueue_recompute('attempt')
    assert inline == []


def test_video_fetch_rejects_external_url_before_network(monkeypatch):
    calls = []
    monkeypatch.setattr(scoring_client.requests, 'get', lambda *a, **kw: calls.append(a))
    with pytest.raises(scoring_client.ScoringError):
        scoring_client.fetch_video_bytes('http://127.0.0.1/private')
    assert calls == []


def test_dispatch_requires_internal_auth_and_reports_outage(client, monkeypatch):
    monkeypatch.setenv('INTERNAL_SECRET', 'test-only')
    calls = []
    def drain():
        calls.append(True)
        return dict(claimed=1, delivered=0, failed=1)
    monkeypatch.setattr(skills, 'drain_scoring_dispatch', drain)
    assert client.post('/skills/dispatch-pending').status_code == 403
    assert calls == []
    response = client.post('/skills/dispatch-pending', headers={'X-Internal-Secret': 'test-only'})
    assert response.status_code == 503
    assert calls == [True]


def test_recompute_rejects_malformed_payload(client, monkeypatch):
    monkeypatch.setenv('INTERNAL_SECRET', 'test-only')
    for payload in ([1], {'attempt_id': 'bad'}, {}):
        assert client.post('/skills/recompute', json=payload,
                           headers={'X-Internal-Secret': 'test-only'}).status_code == 400
