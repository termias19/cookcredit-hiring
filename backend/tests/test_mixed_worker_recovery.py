"""Mixed outbox contention with PostgreSQL and loopback TCP receivers.

No provider credentials, Firebase, Cloud Storage, or staging traffic. Provider
identity/template generation is replaced; durable queues and dispatch are real.
This is a recovery/concurrency test, not an end-to-end capacity certification.
"""
import json
import os
import smtplib
import socketserver
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock, Thread
from time import monotonic

import pytest
import requests
from models import PartnerWebhook, PartnerWebhookDelivery
from models.account_email import AccountEmail
from services import account_email as mail, database, partner_integrations as hooks
from tests.test_report_playback_binding import db

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='isolated database required')


@pytest.mark.parametrize('count', [10, 40, 80])
def test_mixed_workers_recover_without_duplicate_success(db, monkeypatch, count):
    engine = database.SessionLocal.kw['bind']
    for model in (AccountEmail, PartnerWebhook, PartnerWebhookDelivery):
        model.__table__.create(engine)
    lock = Lock()
    mail_tries, mail_success, hook_tries, hook_success = (Counter() for _ in range(4))
    wire_errors, bodies, durations = [], {}, []
    secret = 'isolated-stage4-test-secret'

    class SMTP(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(5)
            self.wfile.write(b'220 localhost test SMTP\r\n')
            recipient = None
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                command = line.decode().strip()
                if command.upper().startswith('RCPT TO:'):
                    recipient = command.split(':', 1)[1].strip('<>')
                if command.upper() == 'DATA':
                    self.wfile.write(b'354 End with dot\r\n')
                    while True:
                        body_line = self.rfile.readline()
                        if body_line == b'.\r\n':
                            break
                        if not body_line:
                            return
                    with lock:
                        mail_tries[recipient] += 1
                        fail = mail_tries[recipient] == 1 and int(recipient.split('@')[0].split('-')[-1]) % 4 == 0
                        if not fail:
                            mail_success[recipient] += 1
                    self.wfile.write(b'451 temporary test outage\r\n' if fail else b'250 accepted\r\n')
                elif command.upper() == 'QUIT':
                    self.wfile.write(b'221 goodbye\r\n')
                    return
                else:
                    self.wfile.write(b'250 localhost\r\n')

    class HTTP(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            event = json.loads(body)
            identity = event['id']
            signature = self.headers['CookCredit-Signature']
            timestamp = int(signature.split(',')[0][2:])
            with lock:
                if signature != hooks._sign(secret, timestamp, body):
                    wire_errors.append('invalid signature')
                if identity in bodies and bodies[identity] != body:
                    wire_errors.append('retry body changed')
                bodies[identity] = body
                hook_tries[identity] += 1
                fail = hook_tries[identity] == 1 and event['data']['index'] % 4 == 0
                if not fail:
                    hook_success[identity] += 1
            self.send_response(503 if fail else 204)
            self.send_header('Content-Length', '0')
            self.end_headers()

    smtp = socketserver.ThreadingTCPServer(('127.0.0.1', 0), SMTP)
    http = ThreadingHTTPServer(('127.0.0.1', 0), HTTP)
    servers = [smtp, http]
    threads = [Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    stop = Event()
    try:
        monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
        monkeypatch.setattr(hooks, 'decrypt_webhook_secret', lambda _: secret)
        endpoint = f'http://127.0.0.1:{http.server_port}/events'

        def deliver(item):
            message = EmailMessage()
            message['From'] = 'test@example.test'
            message['To'] = item.recipient
            message['Subject'] = 'Synthetic local test'
            message.set_content('No real verification link or applicant data.')
            with smtplib.SMTP('127.0.0.1', smtp.server_address[1], timeout=5) as client:
                client.send_message(message)
            return 'sent'

        def send(url, **kwargs):
            assert url == endpoint
            return requests.post(url, **kwargs)

        monkeypatch.setattr(mail, 'deliver_account_email', deliver)
        with database.db_session() as session:
            hook = PartnerWebhook(org_id=db.org, url=endpoint, event_types=['assessment.completed'], secret_ciphertext='synthetic')
            session.add(hook)
            session.flush()
            for index in range(count):
                mail.enqueue_account_email(session, kind='reset', recipient=f'local-{index}@example.test')
                hooks.emit_partner_event(session, org_id=db.org, event_type='assessment.completed', data={'index': index, 'status': 'review-required'})

        def read_during_dispatch():
            while not stop.is_set():
                begin = monotonic()
                with database.db_session() as session:
                    assert session.query(AccountEmail).count() == count
                    assert session.query(PartnerWebhookDelivery).count() == count
                durations.append(monotonic() - begin)

        def drain(kind):
            dispatch = mail.dispatch_account_emails if kind == 'mail' else lambda **kw: hooks.dispatch_partner_webhooks(send=send, **kw)
            for _ in range(count + 1):
                if dispatch(limit=5)['claimed'] == 0:
                    return
            pytest.fail('worker did not drain within bounded rounds')

        with ThreadPoolExecutor(max_workers=7) as pool:
            reader = pool.submit(read_during_dispatch)
            try:
                for phase in range(2):
                    futures = [pool.submit(drain, kind) for kind in ('mail', 'hook') for _ in range(3)]
                    for future in futures:
                        future.result(timeout=60)
                    if phase == 0:
                        with database.db_session() as session:
                            pending_mail = session.query(AccountEmail).filter_by(status='pending').all()
                            pending_hooks = session.query(PartnerWebhookDelivery).filter_by(status='pending').all()
                            assert len(pending_mail) == len(pending_hooks) == (count + 3) // 4
                            for row in pending_mail:
                                assert row.attempts == 1 and row.lease_token is None
                                row.available_at = mail.utcnow() - timedelta(seconds=1)
                            for row in pending_hooks:
                                assert row.attempts == 1 and row.lock_token is None
                                row.next_attempt_at = hooks._utcnow() - timedelta(seconds=1)
            finally:
                stop.set()
                reader.result(timeout=10)

        with database.db_session() as session:
            assert session.query(AccountEmail).filter_by(status='sent').count() == count
            assert session.query(PartnerWebhookDelivery).filter_by(status='delivered').count() == count
        assert len(mail_success) == len(hook_success) == count
        assert set(mail_success.values()) == set(hook_success.values()) == {1}
        assert sum(mail_tries.values()) == sum(hook_tries.values()) == count + (count + 3) // 4
        assert not wire_errors
        assert durations
        print(json.dumps({'jobsPerQueue': count, 'workerDispatchers': 6, 'concurrentReadPairs': len(durations), 'maxReadPairSeconds': round(max(durations), 4), 'retriesPerQueue': (count + 3) // 4, 'duplicateSuccesses': 0}))
    finally:
        stop.set()
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
