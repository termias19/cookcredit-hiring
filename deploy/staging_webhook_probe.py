"""Real HTTPS delivery/retry drill, restricted to the dedicated staging DB."""
import json
import os
import time
import uuid
from datetime import datetime, timezone
import requests

assert os.environ.get('COOKCREDIT_ENVIRONMENT') == 'staging'
assert os.environ.get('CLOUD_SQL_CONNECTION') == 'cookcredit-scoring:us-central1:cookcredit-hiring-stg-db'
assert os.environ.get('DB_USER') == 'hiring_runtime'
receiver = os.environ['PROBE_WEBHOOK_URL']
assert receiver == 'https://cookcredit-hiring-stg-hooktest-915097816203.us-central1.run.app'
origin = os.environ['PUBLIC_API_URL']
assert origin == 'https://cookcredit-hiring-staging-915097816203.us-central1.run.app'
from services.database import init_db, db_session
from services.partner_integrations import encrypt_webhook_secret, emit_partner_event
from services.location import resolve_area
from models import User, Org, PartnerWebhook, PartnerWebhookDelivery
init_db()
assert requests.get(receiver+'/health', timeout=90).status_code == 200
assert requests.post(receiver+'/event', data=b'{"synthetic":true}', timeout=30).status_code == 401
uid, oid, hook_id = 'staging-hook-'+uuid.uuid4().hex, uuid.uuid4(), uuid.uuid4()
try:
    with db_session() as session:
        session.add(User(id=uid, email=uid+'@example.test', name='Synthetic webhook probe', roles=['business']))
        session.flush()
        session.add(Org(id=oid, name='Synthetic webhook drill - not a customer', plan='trial'))
        session.flush()
        session.add(PartnerWebhook(id=hook_id, org_id=oid, url=receiver+'/event', environment='test',
            event_types=['assessment.requested'], created_by=uid,
            secret_ciphertext=encrypt_webhook_secret(os.environ['PROBE_WEBHOOK_SECRET'])))
        session.flush()
        event_id = emit_partner_event(session, org_id=oid, event_type='assessment.requested',
            data={'environment': 'test', 'externalJobId': 'synthetic-cloud-drill', 'externalCandidateId': uid})

    def dispatch():
        result = requests.post(origin+'/api/partner/internal/dispatch-webhooks', json={},
            headers={'X-Internal-Secret': os.environ['INTERNAL_SECRET']}, timeout=90)
        assert result.status_code == 200

    dispatch()
    with db_session() as session:
        row = session.query(PartnerWebhookDelivery).filter_by(webhook_id=hook_id).one()
        assert row.status == 'pending' and row.last_error == 'HTTP 503' and row.attempts == 1
        wait = max(0, (row.next_attempt_at-datetime.now(timezone.utc)).total_seconds())
    time.sleep(wait+1)
    dispatch()
    with db_session() as session:
        row = session.query(PartnerWebhookDelivery).filter_by(webhook_id=hook_id).one()
        assert row.status == 'delivered' and row.attempts == 2 and str(row.event_id) == event_id
        # Deliberate replay of this disposable event, using the same persisted envelope.
        row.status = 'pending'
        row.next_attempt_at = datetime.now(timezone.utc)
    dispatch()
    observed = requests.get(receiver+'/probe/'+event_id,
        headers={'Authorization': 'Bearer '+os.environ['PROBE_WEBHOOK_SECRET']}, timeout=30).json()
    assert observed == {'attempts': '3', 'accepted': '1'}
    area = resolve_area({'postalCode': '10001', 'language': 'EN'}, uid)
    assert area['postalCode'] == '10001' and area['provider'] == 'Google Maps' and area['locationToken']
    print('COOKCREDIT_WEBHOOK_DRILL='+json.dumps({'environment': 'staging', 'eventId': event_id,
        'invalidSignatureRejected': True, 'initial503Retried': True, 'sameEventIdOnReplay': True,
        'deliveries': 3, 'receiverAppliedOnce': True, 'realGoogleZipLookup': True}), flush=True)
finally:
    with db_session() as session:
        hook = session.get(PartnerWebhook, hook_id)
        if hook:
            hook.active = False
            hook.disabled_at = datetime.now(timezone.utc)
