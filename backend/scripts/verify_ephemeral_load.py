"""Synthetic HTTP/SQL load inside the disposable verification build only.

This does not measure Cloud Run, scoring, upload or payment capacity. Rate limiting
is disabled for this capacity probe; it must be tested separately with shared Redis.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cryptography.fernet import Fernet
import requests
from sqlalchemy.engine import make_url


def require_disposable_database():
    url = make_url(os.environ.get('DATABASE_URL', ''))
    if (os.environ.get('COOKCREDIT_EPHEMERAL_VERIFICATION') != '1'
            or url.host != '127.0.0.1' or url.username != 'cookcredit_test'
            or url.database != 'cookcredit_test'):
        raise SystemExit('Only the disposable local verification database is allowed')


def load_app():
    require_disposable_database()
    from app import app
    from extensions import limiter
    limiter.enabled = False
    return app


def main():
    require_disposable_database()
    os.environ.update(COOKCREDIT_ENVIRONMENT='development',
        PARTNER_API_KEY_PEPPER=uuid.uuid4().hex, WEBHOOK_SECRET_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_EMAILS_ENABLED='0', BUSINESS_BILLING_ENABLED='0', BEAM_AGENT_ENABLED='0',
        SCORING_ALLOW_INLINE='0', FRONTEND_URL='http://127.0.0.1:8799',
        DB_POOL_SIZE='4', DB_MAX_OVERFLOW='4')
    from services.database import db_session
    from services.partner_integrations import issue_api_key, encrypt_webhook_secret
    from models import User, Org, RolePosting, PartnerInvitation, OrgAssessmentUsage
    uid, oid, rid = 'load-' + uuid.uuid4().hex, uuid.uuid4(), uuid.uuid4()
    now = datetime.now(timezone.utc)
    with db_session() as session:
        session.add(User(id=uid, email=uid+'@example.test', name='Synthetic load account', roles=['business']))
        session.flush()
        session.add(Org(id=oid, name='Ephemeral load fixture', plan='integration'))
        session.flush()
        session.add(RolePosting(id=rid, org_id=oid, title='Synthetic fixture', status='open',
            integration_managed=True, integration_environment='test', external_job_id='seed-fixture'))
        session.flush()
        key, token = issue_api_key(org_id=oid, name='Disposable verification',
            scopes=['assessments:read', 'assessments:write'], created_by=uid, environment='test')
        session.add(key)
        ciphertext = encrypt_webhook_secret('synthetic-token-unused')
        session.bulk_insert_mappings(PartnerInvitation, [{
            'id': uuid.uuid4(), 'org_id': oid, 'role_posting_id': rid,
            'token_hash': hashlib.sha256(f'{uid}-{i}'.encode()).hexdigest(),
            'token_ciphertext': ciphertext,
            'candidate_email': f'{uid}-{i}@example.test', 'external_candidate_id': f'seed-{i}',
            'external_job_id': 'seed-fixture', 'job_title': 'Synthetic fixture',
            'idempotency_key': f'seed-{i}', 'environment': 'test',
            'expires_at': now + timedelta(days=1), 'created_at': now,
        } for i in range(10000)])
    os.environ['COOKCREDIT_LOAD_TOKEN'] = token
    logs = Path('/tmp/cookcredit-load-server.log').open('w')
    server = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--bind', '127.0.0.1:8799',
        '--workers', '2', '--threads', '4', '--timeout', '60',
        'scripts.verify_ephemeral_load:load_app()'], stdout=logs, stderr=logs)
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError('Synthetic test server exited before becoming ready')
            try:
                if requests.get('http://127.0.0.1:8799/api/health', timeout=1).json().get('database'):
                    break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('Synthetic test server did not become ready')
        reports = []
        workers = int(os.environ.get('LOAD_CLIENTS', '8'))
        rps = float(os.environ.get('LOAD_RPS', '20'))
        assert 1 <= workers <= 100 and 0 < rps <= 200
        for scenario, count in [('requests', 200), ('create', 100), ('retry', 100)]:
            output = Path('/tmp') / f'cookcredit-load-{scenario}.json'
            subprocess.run([sys.executable, 'scripts/hiring_read_load.py',
                '--base-url', 'http://127.0.0.1:8799', '--scenario', scenario,
                '--requests', str(count), '--workers', str(workers), '--rps', str(rps),
                '--output', str(output)], check=True)
            report = json.loads(output.read_text())
            report.update(seedAssessmentRequests=10000, processes=2, threadsPerProcess=4,
                          rateLimitingEnabled=False, infrastructure='ephemeral build VM')
            reports.append(report)
        with db_session() as session:
            usage = session.query(OrgAssessmentUsage).filter_by(org_id=oid, environment='test').one()
            assert usage.request_count == 101, 'Concurrent retries must consume exactly one request'
            assert session.query(PartnerInvitation).filter_by(org_id=oid).count() == 10101
        print('COOKCREDIT_LOAD_REPORT=' + json.dumps(reports), flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
        logs.close()


if __name__ == '__main__':
    main()
