import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hiring_compression import desired_job, derivative_lifecycle


def test_job_is_on_demand_and_excludes_payment_and_mail_credentials():
    service = {'name': 'projects/cookcredit-scoring/locations/us-central1/services/cookcredit-hiring',
        'template': {'serviceAccount': 'existing-runtime@example.test', 'containers': [{'env': [
            {'name': 'FIREBASE_STORAGE_BUCKET', 'value': 'existing-private-bucket'},
            {'name': 'DB_PASS', 'valueSource': {'secretKeyRef': {'secret': 'existing-db-secret', 'version': '1'}}},
            {'name': 'STRIPE_SECRET_KEY', 'value': 'never-copy'},
            {'name': 'SMTP_PASSWORD', 'value': 'never-copy'}]}]}}
    original = copy.deepcopy(service)
    job = desired_job(service, 'production',
        'us-central1-docker.pkg.dev/cookcredit-scoring/cookcredit-hiring/compression@sha256:' + 'a'*64, 'a'*40)
    assert service == original
    task = job['template']['template']
    assert task['serviceAccount'] == 'existing-runtime@example.test'
    assert task['maxRetries'] == 0 and task['timeout'] == '900s'
    names = {e['name'] for e in task['containers'][0]['env']}
    assert 'DB_PASS' in names and 'STRIPE_SECRET_KEY' not in names and 'SMTP_PASSWORD' not in names
    assert 'scaling' not in job['template']
    with pytest.raises(ValueError): desired_job(service, 'staging', 'wrong', 'a'*40)


def test_derivative_expiry_does_not_change_original_retention_rules():
    before = {'lifecycle': {'rule': [{'action': {'type': 'Delete'}, 'condition': {'age': 30,
        'matchesPrefix': ['skill_videos/', 'cookcredit-skill/', 'hiring_cv/']}}]}}
    original = copy.deepcopy(before)
    after = derivative_lifecycle(before)
    assert before == original and after['rule'][0] == before['lifecycle']['rule'][0]
    assert after['rule'][1]['condition'] == {'daysSinceCustomTime': 30, 'matchesPrefix': ['hiring-playback/']}
    assert derivative_lifecycle({'lifecycle': after}) == after
