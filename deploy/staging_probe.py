"""Run as a Cloud Run Job with staging's restricted runtime identity.

Uses only synthetic records and a temporary private text object. It never calls
Stripe, sends email, uploads a person's recording, or changes assessment scores.
The synthetic plan fixture tests the API contract, not payment entitlement sync.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests
from sqlalchemy import text

assert os.environ.get('COOKCREDIT_ENVIRONMENT') == 'staging'
assert os.environ.get('CLOUD_SQL_CONNECTION') == 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-db'
assert os.environ.get('DB_NAME') == 'cookcredit_hiring_staging'
assert os.environ.get('DB_USER') == 'hiring_runtime'
assert os.environ.get('FIREBASE_STORAGE_BUCKET') == 'cookcredit-hiring-stg-media-915097816203'
origin = os.environ['PUBLIC_API_URL']
assert origin == 'https://cookcredit-hiring-staging-915097816203.us-central1.run.app'

from services.database import init_db, db_session
from services.firebase import get_storage_bucket
from services.storage_signing import signed_url
from services.partner_integrations import issue_api_key
from models import User, Org, PartnerApiKey, OrgAssessmentUsage

init_db()
report = {'startedAt': datetime.now(timezone.utc).isoformat(), 'environment': 'staging',
          'scope': 'Cloud metadata, infrastructure and access checks; no live email/payment/assessment walkthrough.'}
ready = requests.get(origin+'/api/ready', timeout=90, allow_redirects=False)
assert ready.status_code == 200 and ready.json()['checks'] == {'database': True, 'rateLimits': True}
report['dependenciesReady'] = True
with db_session() as session:
    assert session.execute(text('SELECT count(*) FROM schema_migrations')).scalar_one() == 27
    assert not session.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar_one()
    assert not session.execute(text("SELECT has_table_privilege(current_user, 'schema_migrations', 'INSERT')")).scalar_one()
report['runtimeCannotChangeSchema'] = True

for path in ('/api/auth/me', '/api/partner/v1/assessment-requests'):
    assert requests.get(origin+path, timeout=30).status_code == 401
for path in ('/api/skills/dispatch-pending', '/api/partner/internal/dispatch-webhooks', '/api/partner/internal/expire-assessment-requests'):
    assert requests.post(origin+path, json={}, timeout=30).status_code == 403
assert requests.post(origin+'/api/stripe/business/checkout', json={}, timeout=30).status_code == 503
assert 'Access-Control-Allow-Origin' not in requests.options(origin+'/api/auth/me', headers={'Origin': 'https://example.invalid'}, timeout=30).headers
allowed_origin = 'https://cookcredit-hiring-staging.web.app'
assert requests.options(origin+'/api/auth/me', headers={'Origin': allowed_origin}, timeout=30).headers.get('Access-Control-Allow-Origin') == allowed_origin
report['unauthenticatedAndCorsChecks'] = True

blob = get_storage_bucket().blob('staging-probes/'+uuid.uuid4().hex+'.txt')
content = b'CookCredit synthetic signed URL check. No applicant data.'
uploaded = False
try:
    upload_url = signed_url(blob, version='v4', expiration=timedelta(minutes=5), method='PUT', content_type='text/plain')
    result = requests.put(upload_url, data=content, headers={'Content-Type': 'text/plain'}, timeout=30)
    assert result.status_code == 200, 'Signed upload failed'
    uploaded = True
    download_url = signed_url(blob, version='v4', expiration=timedelta(minutes=5), method='GET')
    assert requests.get(download_url, timeout=30).content == content
    assert requests.get(blob.public_url, timeout=30).status_code in (401, 403)
    report['privateIamSignedUploadAndDownload'] = True
finally:
    if uploaded:
        blob.delete()

uid, oid = 'staging-probe-'+uuid.uuid4().hex, uuid.uuid4()
key_id = None
try:
    with db_session() as session:
        session.add(User(id=uid, email=uid+'@example.test', name='Synthetic staging probe', roles=['business']))
        session.flush()
        session.add(Org(id=oid, name='Synthetic staging probe - not a customer', plan='integration', created_by=uid))
        session.flush()
        key, token = issue_api_key(org_id=oid, name='Temporary staging cloud verification',
            scopes=['assessments:read', 'assessments:write'], created_by=uid, environment='test')
        session.add(key)
        session.flush()
        key_id = key.id
    child_env = {**os.environ, 'COOKCREDIT_LOAD_TOKEN': token}
    reports = []
    for scenario, count in [('requests', 20), ('create', 8), ('retry', 8)]:
        output = Path('/tmp')/('staging-probe-'+scenario+'.json')
        subprocess.run([sys.executable, 'scripts/hiring_read_load.py', '--base-url', origin,
            '--scenario', scenario, '--requests', str(count), '--workers', '4', '--rps', '4',
            '--timeout', '60', '--output', str(output)], env=child_env, check=True)
        reports.append(json.loads(output.read_text()))
    with db_session() as session:
        usage = session.query(OrgAssessmentUsage).filter_by(org_id=oid, environment='test').one()
        assert usage.request_count == 9, 'Retries must consume only one allowance'
    report['metadataProbes'] = reports
    report['idempotentRetriesConsumeOnce'] = True
    # A bounded burst checks the deployed shared limiter. Align within one fixed
    # minute so a boundary cannot make 120 requests look like a missing limit.
    remaining = 60-time.time() % 60
    if remaining < 20:
        time.sleep(remaining+1)
    def limited_read(_):
        return requests.get(origin+'/api/partner/v1/assessment-requests',
            headers={'Authorization': 'Bearer '+token}, timeout=90).status_code
    with ThreadPoolExecutor(max_workers=12) as pool:
        counts = Counter(pool.map(limited_read, range(80)))
    print('COOKCREDIT_STAGING_BURST='+json.dumps(dict(counts)), flush=True)
    assert set(counts).issubset({200, 429}) and counts[429] > 0, 'Rate-limit burst was not bounded cleanly'
    report['boundedBurstStatusCounts'] = dict(counts)
    report['sharedLimiterRejectsExcessTraffic'] = True
finally:
    # Retain synthetic request/audit records for inspection, but remove the
    # temporary fixture's access even if a probe assertion failed.
    with db_session() as session:
        if key_id:
            key = session.get(PartnerApiKey, key_id)
            if key:
                key.revoked_at = datetime.now(timezone.utc)
        org = session.get(Org, oid)
        if org:
            org.plan = 'trial'

# Exercise the real queue and delegated OIDC identity against the harmless
# expiry maintenance endpoint. This proves delivery plumbing, not scoring.
from google.cloud import tasks_v2
task = tasks_v2.CloudTasksClient().create_task(parent=os.environ['TASKS_QUEUE'], task={
    'name': os.environ['TASKS_QUEUE']+'/tasks/staging-probe-'+uuid.uuid4().hex,
    'http_request': {'http_method': tasks_v2.HttpMethod.POST,
        'url': origin+'/api/partner/internal/expire-assessment-requests',
        'headers': {'Content-Type': 'application/json'}, 'body': b'{}',
        'oidc_token': {'service_account_email': os.environ['TASKS_OIDC_SA'], 'audience': origin}}})
report['queueProbeTask'] = task.name
print('COOKCREDIT_STAGING_PROBE='+json.dumps(report), flush=True)
