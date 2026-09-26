"""Three-minute, 20-tenant metadata exercise. No email, payments or videos."""
import json
import os
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import requests
from services.database import init_db, db_session
from scripts.hiring_read_load import assessment_request_body
from services.partner_integrations import issue_api_key
from models import User, Org, PartnerApiKey, OrgAssessmentUsage

assert os.environ['COOKCREDIT_ENVIRONMENT'] == 'staging'
assert os.environ['CLOUD_SQL_CONNECTION'] == 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-db'
origin = os.environ['PUBLIC_API_URL']
assert origin == 'https://cookcredit-hiring-staging-915097816203.us-central1.run.app'
health = requests.get(origin+'/api/health', timeout=30).json()
assert health['environment'] == 'staging' and health['app'] == 'CookCredit'
init_db()
run_id = 'sustained-'+uuid.uuid4().hex
fixtures, jobs = [], []
report = {'runId': run_id, 'target': origin, 'revision': health.get('revision'),
    'startedAt': datetime.now(timezone.utc).isoformat(), 'tenants': 20, 'workers': 16,
    'targetRps': 10, 'durationSeconds': 180,
    'scope': 'Authenticated multi-tenant metadata reads/creation/idempotent retries. No video or scorer capacity claim.'}
try:
    with db_session() as session:
        for index in range(20):
            uid, oid = run_id+'-'+str(index), uuid.uuid4()
            session.add(User(id=uid, email=uid+'@example.test', name='Synthetic sustained staging test', roles=['business']))
            session.flush()
            session.add(Org(id=oid, name='Synthetic sustained staging test', plan='integration', created_by=uid))
            session.flush()
            key, token = issue_api_key(org_id=oid, name='Temporary sustained verification',
                scopes=['assessments:read', 'assessments:write'], created_by=uid, environment='test')
            session.add(key); session.flush()
            fixtures.append({'oid': oid, 'key_id': key.id, 'token': token})
    # Each tenant gets 18 unique requests, 18 retries and 54 reads. Create/retry
    # runs before its tenant's next round, allowing exact idempotency checks.
    for round_no in range(90):
        kind = 'create' if round_no % 5 == 0 else 'retry' if round_no % 5 == 1 else 'read'
        for tenant in range(20):
            jobs.append((tenant, kind, round_no // 5))
    start = time.monotonic()
    def request_one(item):
        index, (tenant, kind, identity) = item
        delay = start+index/10-time.monotonic()
        if delay > 0: time.sleep(delay)
        headers = {'Authorization': 'Bearer '+fixtures[tenant]['token']}
        begin = time.monotonic()
        rid = None
        try:
            url = origin+'/api/partner/v1/assessment-requests'
            if kind == 'read':
                response = requests.get(url, headers=headers, timeout=30, allow_redirects=False)
            else:
                body = assessment_request_body(run_id, f'{tenant}-{identity}')
                response = requests.post(url, json=body,
                    headers={**headers, 'Idempotency-Key': f'{run_id}-{tenant}-{identity}'},
                    timeout=30, allow_redirects=False)
            status = response.status_code
            if 200 <= status < 300:
                data = response.json()
                if kind != 'read':
                    rid = data.get('data', {}).get('id')
                    if not rid or data['data'].get('environment') != 'test': status = -2
        except (requests.RequestException, ValueError):
            status = 0
        return {'tenant': tenant, 'kind': kind, 'identity': identity, 'status': status,
            'milliseconds': 1000*(time.monotonic()-begin), 'requestId': rid}
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(request_one, enumerate(jobs)))
    report.update(requests=len(results), achievedRps=round(len(results)/(time.monotonic()-start), 2),
                  statusCounts=dict(Counter(row['status'] for row in results)))
    by_kind, ids = defaultdict(list), defaultdict(set)
    for row in results:
        by_kind[row['kind']].append(row['milliseconds'])
        if row['requestId']: ids[(row['tenant'], row['identity'])].add(row['requestId'])
    report['latencyMs'] = {kind: {'p50': round(sorted(values)[int(len(values)*.5)], 2),
                                'p95': round(sorted(values)[int(len(values)*.95)], 2),
                                'p99': round(sorted(values)[int(len(values)*.99)], 2)}
                           for kind, values in by_kind.items()}
    report['errors'] = sum(not 200 <= row['status'] < 300 for row in results)
    report['idempotencyPassed'] = len(ids) == 360 and all(len(values) == 1 for values in ids.values())
    with db_session() as session:
        counts = [session.query(OrgAssessmentUsage).filter_by(org_id=f['oid'], environment='test').one().request_count
                  for f in fixtures]
    report['usageCountPassed'] = counts == [18]*20
    assert report['errors'] == 0 and report['idempotencyPassed'] and report['usageCountPassed']
finally:
    with db_session() as session:
        for fixture in fixtures:
            key = session.get(PartnerApiKey, fixture['key_id'])
            if key: key.revoked_at = datetime.now(timezone.utc)
            org = session.get(Org, fixture['oid'])
            if org: org.plan = 'trial'
    report['temporaryKeysRevoked'] = True
    print('COOKCREDIT_SUSTAINED='+json.dumps(report), flush=True)
