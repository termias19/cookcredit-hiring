"""No-network checks for derivative binding, expiry and original fallback."""
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from services import recording_compression as compression


@pytest.mark.parametrize('job', ['https://evil.test', 'projects/toqto-prod/locations/us-central1/jobs/x',
                                'projects/cookcredit-scoring/locations/us-central1/jobs/cc-home-prod-check'])
def test_job_target_is_closed_to_other_projects_and_jobs(job, monkeypatch):
    monkeypatch.setenv('HIRING_COMPRESSION_JOB', job)
    with pytest.raises(RuntimeError, match='configuration'):
        compression.launch_job(str(uuid.uuid4()), str(uuid.uuid4()))


@pytest.mark.parametrize('field,value', [('profile', 'unknown'), ('originalGeneration', '999'),
    ('generation', 'https://evil.test'), ('expiresAt', '2099-01-01T00:00:00+00:00')])
def test_forged_derivative_never_reaches_storage(field, value, monkeypatch):
    from services import firebase
    monkeypatch.setenv('HIRING_COMPRESSED_PLAYBACK', '1')
    monkeypatch.setattr(firebase, 'get_storage_bucket', lambda: pytest.fail('No storage call permitted'))
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    derivative = {'profile': compression.PROFILE, 'generation': '321', 'originalGeneration': '123',
                  'expiresAt': expires.isoformat(), field: value}
    assert compression.compressed_playback_url('unused', '123', 'cook', derivative, expires) is None


def test_disabled_derivative_returns_original_without_storage(monkeypatch):
    monkeypatch.delenv('HIRING_COMPRESSED_PLAYBACK', raising=False)
    assert compression.compressed_playback_url('unused', '123', 'cook', {}, None) is None


def test_derivative_identity_changes_with_source_generation():
    path = 'cookcredit-skill/users/cook/assessments/example/recording.mp4'
    assert compression.derivative_path(path, '123') == compression.derivative_path(path, '123')
    assert compression.derivative_path(path, '123') != compression.derivative_path(path, '124')
    assert 'cook/' not in compression.derivative_path(path, '123')


def test_decoder_does_not_inherit_server_secrets(monkeypatch):
    import os, sys
    from scripts.inspect_hiring_video import run
    monkeypatch.setenv('DB_PASS', 'never-pass-to-decoder')
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'never-pass-to-decoder')
    output = run([sys.executable, '-c',
        'import os; print("DB_PASS" in os.environ or "STRIPE_SECRET_KEY" in os.environ)'], 5)
    assert output.strip() == 'False'
