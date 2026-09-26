"""Cloud Tasks request contract, without network or Google credentials."""
import sys
import pytest
from types import SimpleNamespace

from google.api_core.exceptions import AlreadyExists
from services.skill_attempts import _enqueue_cloud_task
from services.scoring_dispatch import validate_dispatch_configuration


def test_task_names_deadline_auth_and_bounded_create(monkeypatch):
    calls = []
    def create_task(**kw):
        calls.append(kw)
        if len(calls) == 2:
            raise AlreadyExists('same dispatch was already accepted')
    fake = SimpleNamespace(HttpMethod=SimpleNamespace(POST=1),
                           CloudTasksClient=lambda: SimpleNamespace(create_task=create_task))
    monkeypatch.setitem(sys.modules, 'google.cloud.tasks_v2', fake)
    monkeypatch.setenv('INTERNAL_SECRET', 'only-test-secret')
    monkeypatch.setenv('TASKS_OIDC_SA', 'worker@example.test')
    monkeypatch.delenv('TASKS_OIDC_AUDIENCE', raising=False)
    for token in ('delivery-1', 'delivery-1', 'recovery-2'):
        _enqueue_cloud_task('attempt-1', 'projects/test/locations/test/queues/test',
                            'https://worker.example.test/recompute', dispatch_id=token)
    first, duplicate, recovered = [c['request']['task'] for c in calls]
    assert first['name'] == duplicate['name']
    assert first['name'] != recovered['name']
    assert first['dispatch_deadline']['seconds'] == 1800
    assert first['http_request']['headers']['X-Internal-Secret'] == 'only-test-secret'
    assert first['http_request']['oidc_token']['service_account_email'] == 'worker@example.test'
    assert first['http_request']['oidc_token']['audience'] == 'https://worker.example.test'
    assert all(c['retry'] is None and c['timeout'] == 30 for c in calls)


def test_cloud_run_requires_durable_dispatch_configuration(monkeypatch):
    monkeypatch.setenv('K_SERVICE', 'test-service')
    for key in ('TASKS_QUEUE', 'TASKS_TARGET_URL', 'TASKS_OIDC_SA', 'INTERNAL_SECRET', 'SCORING_ALLOW_INLINE'):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match='Missing scoring dispatch settings'):
        validate_dispatch_configuration()
    valid = dict(TASKS_QUEUE='projects/test/locations/us-central1/queues/scoring',
                 TASKS_TARGET_URL='https://test.run.app/api/skills/recompute',
                 TASKS_OIDC_SA='worker@test.iam.gserviceaccount.com', INTERNAL_SECRET='test-only')
    for key, value in valid.items():
        monkeypatch.setenv(key, value)
    validate_dispatch_configuration()
    for key, value in dict(TASKS_QUEUE='scoring', TASKS_TARGET_URL='http://test/api/skills/recompute',
                           TASKS_OIDC_SA='person@example.test', SCORING_ALLOW_INLINE='1').items():
        with monkeypatch.context() as change:
            change.setenv(key, value)
            with pytest.raises(RuntimeError):
                validate_dispatch_configuration()


def test_local_tests_need_no_dispatch_secrets(monkeypatch):
    monkeypatch.delenv('K_SERVICE', raising=False)
    monkeypatch.delenv('TASKS_QUEUE', raising=False)
    validate_dispatch_configuration()
