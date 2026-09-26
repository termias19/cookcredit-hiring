"""Sustained integrated workload on disposable PostGIS and an isolated test bucket only.

Reuses the Stage 4 workload: actual hiring routes, SQL, import streaming, GCS, overlay, CV, projections and
outboxes. Firebase identity/source metadata and SMTP/HTTPS providers are local
test adapters; no real user account or email is used. This is a bounded backend
launch envelope, not a browser/network/Firebase-auth benchmark.
"""
import base64
import hashlib
import io
import json
import os
import smtplib
import socketserver
import struct
import time
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock, Thread
from types import SimpleNamespace
from urllib.parse import unquote

from sqlalchemy.engine import make_url
url = make_url(os.environ.get('DATABASE_URL', ''))
if not __debug__:
    raise SystemExit('Run verification without Python optimization; verification assertions are required.')
if (os.environ.get('COOKCREDIT_EPHEMERAL_VERIFICATION') != '1'
        or url.host != '127.0.0.1' or url.username != 'cookcredit_test'
        or url.database != 'cookcredit_test' or os.environ.get('CLOUD_SQL_CONNECTION')
        or os.environ.get('FIREBASE_STORAGE_BUCKET') != 'cookcredit-hiring-load-915097816203'):
    raise SystemExit('Only the disposable local database and private load-test bucket are allowed.')
import resource
from cryptography.fernet import Fernet
os.environ['WEBHOOK_SECRET_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
os.environ['PARTNER_API_KEY_PEPPER'] = uuid.uuid4().hex
os.environ['FRONTEND_URL'] = 'http://127.0.0.1:8799'
os.environ['FIREBASE_USE_ADC'] = '1'
os.environ['FIREBASE_PROJECT_ID'] = 'cookcredit-scoring'
os.environ.update(COOKCREDIT_ENVIRONMENT='development', HIRING_ACCESS_APPROVALS_ENABLED='0',
    AUTH_APP_CHECK_REQUIRED='0', AUTH_EMAILS_ENABLED='0', BUSINESS_BILLING_ENABLED='0',
    ENGINE_APPLICANT_IMPORT_ENABLED='1', ASSESSMENT_BRIDGE_ENABLED='1', SCORING_ALLOW_INLINE='0',
    RATELIMIT_STORAGE_URI='memory://', COOKCREDIT_EXPECT_MULTI_INSTANCE='0')

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from flask import Flask
from sqlalchemy import text
from extensions import limiter
from middleware import auth
from models import User, Org, OrgMembership, RolePosting, HiringApplication, SkillAttempt, PartnerWebhook, PartnerWebhookDelivery
from models.account_email import AccountEmail
from routes import hiring, business
from services import database, engine_recording_import as importer, account_email as mail, partner_integrations as hooks, skill_attempts
from services.firebase import get_storage_bucket

database.init_db()
with database.db_session() as session:
    migration_count = session.execute(text('SELECT count(*) FROM schema_migrations')).scalar()
    assert migration_count >= 29
    assert session.execute(text("SELECT to_regclass('hiring_applications') IS NOT NULL")).scalar()
RUN = 's5-' + uuid.uuid4().hex
EMPLOYERS = [RUN + '-employer-' + str(i) for i in range(4)]
APPLICANTS = int(os.environ.get('LOAD_APPLICANTS', '240'))
assert APPLICANTS in (8, 240)
CONCURRENT = 8
INTERVAL = 10
COOKS = [RUN + '-cook-' + str(i) for i in range(APPLICANTS)]
allowed = set(EMPLOYERS + COOKS)
def identity(token):
    assert token in allowed
    return {'uid': token, 'email': token + '@example.test', 'name': 'Synthetic test', 'email_verified': True}
auth._verify_token = identity
limiter.enabled = False
app = Flask('isolated-stage4')
app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
app.register_blueprint(hiring.hiring_bp, url_prefix='/hiring')
app.register_blueprint(business.business_bp, url_prefix='/business')
bucket = get_storage_bucket()
clip = base64.b64decode('AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAQjbW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAAB9AAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAA010cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAB9AAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAUAAAADwAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAfQAAAIAAABAAAAAALFbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAoAAAAUABVxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAACcG1pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAAjBzdGJsAAAAwHN0c2QAAAAAAAAAAQAAALBhdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAUAA8ABIAAAASAAAAAAAAAABFUxhdmM2Mi4yOC4xMDAgbGlieDI2NAAAAAAAAAAAAAAAGP//AAAANmF2Y0MBZAAM/+EAGWdkAAys2UFB+wEQAAADABAAAAMBQPFCmWABAAZo6+PLIsD9+PgAAAAAEHBhc3AAAAABAAAAAQAAABRidHJ0AAAAAAAAEMQAAAAAAAAAGHN0dHMAAAAAAAAAAQAAABQAAAQAAAAAFHN0c3MAAAAAAAAAAQAAAAEAAACoY3R0cwAAAAAAAAATAAAAAQAACAAAAAABAAAUAAAAAAEAAAgAAAAAAQAAAAAAAAABAAAEAAAAAAEAABQAAAAAAQAACAAAAAABAAAAAAAAAAEAAAQAAAAAAQAAFAAAAAABAAAIAAAAAAEAAAAAAAAAAQAABAAAAAABAAAUAAAAAAEAAAgAAAAAAQAAAAAAAAABAAAEAAAAAAEAABAAAAAAAgAABAAAAAAcc3RzYwAAAAAAAAABAAAAAQAAABQAAAABAAAAZHN0c3oAAAAAAAAAAAAAABQAAAL4AAAAEQAAAA4AAAAOAAAADgAAABcAAAAQAAAADgAAAA4AAAAXAAAAEAAAAA4AAAAOAAAAFwAAABAAAAAOAAAADgAAABcAAAAQAAAADgAAABRzdGNvAAAAAAAAAAEAAARTAAAAYnVkdGEAAABabWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAbWRpcmFwcGwAAAAAAAAAAAAAAAAtaWxzdAAAACWpdG9vAAAAHWRhdGEAAAABAAAAAExhdmY2Mi4xMi4xMDAAAAAIZnJlZQAABDltZGF0AAACrgYF//+q3EXpvebZSLeWLNgg2SPu73gyNjQgLSBjb3JlIDE2NSByMzIyMyAwNDgwY2IwIC0gSC4yNjQvTVBFRy00IEFWQyBjb2RlYyAtIENvcHlsZWZ0IDIwMDMtMjAyNSAtIGh0dHA6Ly93d3cudmlkZW9sYW4ub3JnL3gyNjQuaHRtbCAtIG9wdGlvbnM6IGNhYmFjPTEgcmVmPTMgZGVibG9jaz0xOjA6MCBhbmFseXNlPTB4MzoweDExMyBtZT1oZXggc3VibWU9NyBwc3k9MSBwc3lfcmQ9MS4wMDowLjAwIG1peGVkX3JlZj0xIG1lX3JhbmdlPTE2IGNocm9tYV9tZT0xIHRyZWxsaXM9MSA4eDhkY3Q9MSBjcW09MCBkZWFkem9uZT0yMSwxMSBmYXN0X3Bza2lwPTEgY2hyb21hX3FwX29mZnNldD0tMiB0aHJlYWRzPTcgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZyYW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRiPTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTIga2V5aW50PTI1MCBrZXlpbnRfbWluPTEwIHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRpbz0xLjQwIGFxPTE6MS4wMACAAAAAQmWIhAAR//7n4/wKbXzEcTp2GPr31tdyoujXh1cYhTyC6Mxkf19QAF7xKsX1bfTg8l/gUUAABCgiEzWymSzeLCSczwAAAA1BmiRsQR/+tSqAAA5YAAAACkGeQniHfwAAN+EAAAAKAZ5hdEN/AABQQAAAAAoBnmNqQ38AAFBBAAAAE0GaaEmoQWiZTAgj//61KoAADlkAAAAMQZ6GRREsO/8AADfhAAAACgGepXRDfwAAUEEAAAAKAZ6nakN/AABQQAAAABNBmqxJqEFsmUwIIf/+qlUAABywAAAADEGeykUVLDv/AAA34QAAAAoBnul0Q38AAFBAAAAACgGe62pDfwAAUEAAAAATQZrwSahBbJlMCH///qmWAABvwQAAAAxBnw5FFSw7/wAAN+EAAAAKAZ8tdEN/AABQQQAAAAoBny9qQ38AAFBAAAAAE0GbM0moQWyZTAhv//6nhAAA3oAAAAAMQZ9RRRUsN/8AAFBBAAAACgGfcmpDfwAAUEA=')
padding = 4 * 1024 * 1024 - len(clip)
video = clip + struct.pack('>I4s', padding, b'free') + bytes(padding - 8)
video_hash = hashlib.sha256(video).hexdigest()
pdf = b'%PDF-1.4\nSynthetic Stage 4 CV. No personal data.\n%%EOF'
overlay = {'version': 2, 'timebase': 'recording-ms', 'mirrored': False,
    'renderer': '741f6ae7cb43556404b49820f460c0a59f914b7bd25dc3414e19397c196bafa1',
    'frames': [[i * 100, None, None, {'width': 1280, 'height': 720, 'bladeExtendK': 1,
        'knifePresent': False, 'knifeConf': 0, 'knifeWorker': False, 'bladeTrail': []}] for i in range(241)]}
lock, stop = Lock(), Event()
latencies, successes, hook_events = defaultdict(list), Counter(), Counter()
created_objects = set()
application_ids = []
hook_ids = []
roles = []
errors = []
queue_samples = []
pool_samples = []


class SMTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        self.wfile.write(b'220 localhost stage4\r\n')
        recipient = ''
        while True:
            line = self.rfile.readline()
            if not line:
                return
            cmd = line.decode().strip()
            if cmd.upper().startswith('RCPT TO:'):
                recipient = cmd.split(':', 1)[1].strip('<>')
            if cmd.upper() == 'DATA':
                self.wfile.write(b'354 continue\r\n')
                while True:
                    row = self.rfile.readline()
                    if row == b'.\r\n':
                        break
                    if not row:
                        return
                assert recipient.startswith(RUN) and recipient.endswith('@example.test')
                with lock:
                    successes[recipient] += 1
                self.wfile.write(b'250 accepted\r\n')
            elif cmd.upper() == 'QUIT':
                self.wfile.write(b'221 bye\r\n')
                return
            else:
                self.wfile.write(b'250 okay\r\n')


class HTTP(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith('/object/'):
            from urllib.parse import urlsplit, parse_qs
            parsed = urlsplit(self.path)
            name = unquote(parsed.path[len('/object/'):])
            assert any(name.startswith('cookcredit-skill/users/' + uid + '/') for uid in COOKS)
            generation = int(parse_qs(parsed.query)['generation'][0])
            obj = bucket.blob(name, generation=generation)
            data = obj.download_as_bytes(if_generation_match=generation, timeout=60)
            self.send_response(200); self.send_header('Content-Length', str(len(data)))
            self.end_headers(); self.wfile.write(data); return
        assert self.path == '/source' 
        self.send_response(200)
        self.send_header('Content-Length', str(len(video)))
        self.send_header('x-goog-generation', '123')
        self.end_headers()
        self.wfile.write(video)

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        event = json.loads(body)
        signature = self.headers['CookCredit-Signature']
        timestamp = int(signature.split(',')[0][2:])
        assert signature == hooks._sign('stage4-local-secret', timestamp, body)
        with lock:
            hook_events[event['id']] += 1
        self.send_response(204)
        self.send_header('Content-Length', '0')
        self.end_headers()


smtp = socketserver.ThreadingTCPServer(('127.0.0.1', 0), SMTP)
http = ThreadingHTTPServer(('127.0.0.1', 0), HTTP)
for server in (smtp, http):
    Thread(target=server.serve_forever, daemon=True).start()
endpoint = f'http://127.0.0.1:{http.server_port}'
# Real private GCS downloads through a loopback adapter. IAM URL signing is not measured.
from services import assessment_media, landmark_recording
from urllib.parse import quote
def local_playback(blob, **kwargs):
    assert blob.bucket.name == os.environ['FIREBASE_STORAGE_BUCKET']
    assert any(blob.name.startswith('cookcredit-skill/users/' + uid + '/') for uid in COOKS)
    return endpoint + '/object/' + quote(blob.name, safe='') + '?generation=' + str(blob.generation)
assessment_media.signed_url = local_playback
landmark_recording.signed_url = local_playback


def record(uid, assessment_id, **kwargs):
    assert uid in COOKS and assessment_id == uid + '-assessment'
    return {'userId': uid, 'assessmentId': assessment_id, 'status': 'ready', 'mode': 'assessment',
        'storagePath': f'cookcredit-skill/users/{uid}/assessments/{assessment_id}/recording.mp4',
        'mimeType': 'video/mp4', 'sizeBytes': len(video), 'consentEvidence': {'dataAndBiometric': True, 'age18Plus': True},
        'score': 70, 'metrics': {'rhythm': 70, 'consistency': 70, 'form': 70}, 'strokes': 20, 'cadence': 1}


def source_metadata(url, headers):
    path = unquote(url.split('/o/', 1)[1])
    parts = path.split('/')
    assert parts[2] in COOKS and parts[4] == parts[2] + '-assessment'
    return {'bucket': importer.SOURCE_BUCKET, 'name': path, 'generation': '123', 'size': str(len(video)),
        'contentType': 'video/mp4', 'metadata': {'ownerUid': parts[2], 'assessmentId': parts[4]}}


def source_get(url, **kwargs):
    source_metadata(url, {})
    assert kwargs.get('params') == {'alt': 'media', 'generation': '123'}
    return requests.get(endpoint + '/source', stream=True, timeout=(5, 60))


importer.read_owned_record = record
importer._json_get = source_metadata
importer.requests = SimpleNamespace(get=source_get, RequestException=requests.RequestException)


def deliver(item):
    if not item.recipient.startswith(RUN):
        return 'skipped'  # Restored outbox entries must never reach real recipients.
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = 'stage4@example.test', item.recipient, 'Synthetic local test'
    msg.set_content('No real verification link.')
    with smtplib.SMTP('127.0.0.1', smtp.server_address[1], timeout=10) as client:
        client.send_message(msg)
    return 'sent'


mail.deliver_account_email = deliver
def send(url, **kwargs):
    if url != endpoint + '/event':
        return SimpleNamespace(status_code=503)
    return requests.post(url, **kwargs)


with database.db_session() as session:
    for uid in EMPLOYERS + COOKS:
        session.add(User(id=uid, email=uid + '@example.test', name='Synthetic test', roles=['business'] if uid in EMPLOYERS else ['cook']))
    session.flush()
    for uid in EMPLOYERS:
        org = Org(id=uuid.uuid4(), name='Isolated Stage 4', plan='trial')
        session.add(org); session.flush()
        session.add(OrgMembership(org_id=org.id, user_id=uid, seat_role='admin'))
        role = RolePosting(id=uuid.uuid4(), org_id=org.id, title='Synthetic isolated workload', status='open',
            requirements={'assessmentCriteria': {'profileVersion': 'knife-motion-v1', 'minimumRhythm': 60}})
        session.add(role); roles.append(role.id)
        hook = PartnerWebhook(id=uuid.uuid4(), org_id=org.id, url=endpoint + '/event',
            event_types=['application.submitted', 'assessment.started', 'assessment.processing', 'assessment.completed'],
            secret_ciphertext=hooks.encrypt_webhook_secret('stage4-local-secret'))
        session.add(hook); hook_ids.append(hook.id)


def call(client, uid, path, *, method='GET', kind='metadata', expected=200, **kwargs):
    started = time.monotonic()
    response = client.open(path, method=method, headers={'Authorization': 'Bearer ' + uid}, **kwargs)
    with lock:
        latencies[kind].append(time.monotonic() - started)
    assert response.status_code == expected, (path.split('/')[1], response.status_code, response.json)
    return response


def workers():
    while not stop.is_set():
        with database.db_session() as session:
            pending = session.query(SkillAttempt.id).filter(SkillAttempt.user_id.in_(COOKS), SkillAttempt.verification_state == 'PROVISIONAL').all()
        for (aid,) in pending:
            skill_attempts.run_recompute(str(aid))
        with database.db_session() as session:
            email_pending = session.query(AccountEmail).filter(AccountEmail.recipient.like(RUN + '%'), AccountEmail.status.in_(['pending', 'sending'])).count()
            hook_pending = session.query(PartnerWebhookDelivery).filter(PartnerWebhookDelivery.webhook_id.in_(hook_ids), PartnerWebhookDelivery.status.in_(['pending', 'delivering'])).count()
        queue_samples.append((email_pending, hook_pending))
        pool_samples.append(database.engine.pool.checkedout())
        mail.dispatch_account_emails(limit=5)
        hooks.dispatch_partner_webhooks(send=send, limit=50)
        stop.wait(.1)


def employer_reads():
    with app.test_client() as client:
        while not stop.is_set():
            for i, uid in enumerate(EMPLOYERS):
                call(client, uid, f'/hiring/roles/{roles[i]}/applications')
            stop.wait(.4)


def applicant(index):
    time.sleep(max(0, start + (index // CONCURRENT) * INTERVAL - time.monotonic()))
    uid = COOKS[index]
    owner = EMPLOYERS[index % 4]
    with app.test_client() as client:
        body = {'fullName': 'Synthetic Cook', 'acceptedEvidenceShare': True,
            'consentVersion': hiring.APPLICATION_CONSENT_VERSION, 'answers': {}}
        applied = call(client, uid, f'/hiring/roles/{roles[index % 4]}/apply', method='POST', kind='application', expected=201,
            data={'application': json.dumps(body), 'cv': (io.BytesIO(pdf), 'cv.pdf')}).json['application']
        aid = applied['id']
        with lock:
            application_ids.append(aid)
        with database.db_session() as session:
            mail.enqueue_account_email(session, kind='reset', recipient=uid + '@example.test')
        started = call(client, uid, f'/hiring/applications/{aid}/attempts/start', method='POST', expected=201).json
        complete = call(client, uid, f'/hiring/assessment-sessions/{started["sessionId"]}/complete', method='POST', kind='import', expected=202,
            json={'assessmentId': uid + '-assessment', 'originalLandmarks': overlay}).json
        retry = call(client, uid, f'/hiring/assessment-sessions/{started["sessionId"]}/complete', method='POST',
            json={'assessmentId': uid + '-assessment', 'originalLandmarks': overlay}).json
        assert retry['attemptId'] == complete['attemptId']
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = call(client, uid, f'/hiring/assessment-sessions/{started["sessionId"]}').json['session']
            if response['status'] == 'completed':
                break
            time.sleep(.2)
        else:
            raise AssertionError('Processing exceeded 60 seconds')
        assert call(client, owner, f'/hiring/applications/{aid}/cv', kind='cv').data == pdf
        playback = call(client, owner, f'/business/candidate/{uid}/video?attemptId={complete["attemptId"]}&landmarks=1', kind='playback').json
        with requests.get(playback['videoUrl'], timeout=60) as response:
            assert response.status_code == 200 and hashlib.sha256(response.content).hexdigest() == video_hash
        with requests.get(playback['landmarksUrl'], timeout=30) as response:
            assert response.status_code == 200 and response.json() == overlay
        call(client, EMPLOYERS[(index + 1) % 4], f'/business/candidate/{uid}/video', expected=403)
        return complete['attemptId']


start = time.monotonic()
try:
    with ThreadPoolExecutor(max_workers=CONCURRENT + 2) as pool:
        worker = pool.submit(workers)
        reader = pool.submit(employer_reads)
        try:
            results = list(pool.map(applicant, range(APPLICANTS)))
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                with database.db_session() as session:
                    remaining = session.query(PartnerWebhookDelivery).filter(PartnerWebhookDelivery.webhook_id.in_(hook_ids), PartnerWebhookDelivery.status != 'delivered').count()
                if len(successes) == APPLICANTS and remaining == 0:
                    break
                time.sleep(.5)
            assert len(successes) == APPLICANTS and set(successes.values()) == {1}
            assert remaining == 0 and hook_events and set(hook_events.values()) == {1}
            assert len(set(results)) == APPLICANTS
        finally:
            stop.set()
            worker.result(timeout=60); reader.result(timeout=30)
    def percentile(values, p):
        return sorted(values)[min(len(values) - 1, int((len(values) - 1) * p))]
    metrics = {key: {'count': len(values), 'p95Seconds': round(percentile(values, .95), 4),
        'p99Seconds': round(percentile(values, .99), 4), 'maxSeconds': round(max(values), 4)} for key, values in latencies.items()}
    assert metrics['metadata']['p95Seconds'] < 2
    assert metrics['import']['p95Seconds'] < 15
    assert metrics['application']['p95Seconds'] < 5
    report = {'runId': RUN, 'applicants': APPLICANTS, 'employers': 4, 'concurrentApplicants': CONCURRENT,
        'bytesPerRecording': len(video), 'elapsedSeconds': round(time.monotonic() - start, 3),
        'latency': metrics, 'maxResidentMemoryMiB': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2),
        'cpuSeconds': round(resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime, 2),
        'maxObservedCheckedOutConnections': max(pool_samples),
        'maxObservedEmailBacklog': max(i[0] for i in queue_samples), 'maxObservedWebhookBacklog': max(i[1] for i in queue_samples),
        'finalUndeliveredWebhooks': remaining, 'emailsDeliveredLocally': len(successes), 'webhooksDeliveredLocally': len(hook_events),
        'duplicateDeliveries': 0, 'crossCompanyPlaybackDenied': True, 'disposableMigrationCount': migration_count,
        'authentication': 'Synthetic test identities; no Firebase sign-in or browser network benchmark',
        'source': 'Local synthetic video endpoint; real import pipeline and private GCS destination',
        'providers': 'Local SMTP/HTTP and loopback playback URLs; no provider quota, Firebase auth, or IAM signing capacity claim',
        'database': 'Disposable PostGIS; does not size production shared-core Cloud SQL',
        'rateLimits': 'Disabled for capacity; separate shared Redis regression applies'}
    assert report['maxResidentMemoryMiB'] < 768
    print('STAGE5_INTEGRATED_RESULT=' + json.dumps(report), flush=True)
finally:
    stop.set()
    for server in (http, smtp):
        server.shutdown(); server.server_close()
    cleanup_errors = 0
    for uid in COOKS:
        for blob in bucket.list_blobs(prefix=f'cookcredit-skill/users/{uid}/'):
            try:
                blob.delete(if_generation_match=blob.generation, timeout=20)
            except Exception:
                cleanup_errors += 1
    for aid in application_ids:
        for blob in bucket.list_blobs(prefix=f'hiring_cv/{aid}/'):
            try:
                blob.delete(if_generation_match=blob.generation, timeout=20)
            except Exception:
                cleanup_errors += 1
    print('STAGE5_INTEGRATED_CLEANUP=' + json.dumps({'runId': RUN, 'errors': cleanup_errors}), flush=True)
    assert cleanup_errors == 0
