"""Exercise access migrations in disposable local schemas, never live data."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from services import database
from services.database import db_session
from services import hiring_access as access, account_email
from models.hiring_access import HiringAccessRequest, HiringAccessEvent
from models.account_email import AccountEmail
from middleware import auth
from routes.hiring_access import access_bp

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local test database required')


@pytest.fixture
def db(monkeypatch):
    # Access approval has no dependency on spatial tables. Exercise its real
    # migrations in a dedicated schema without requiring the marketplace fixture.
    url = os.environ['HIRING_TEST_DATABASE_URL']
    parsed = make_url(url)
    if parsed.host not in ('127.0.0.1', 'localhost') or parsed.username != 'cookcredit_test':
        pytest.fail('Only the dedicated local cookcredit_test database is allowed')
    schema = 'access_test_' + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public'})
    try:
        with engine.begin() as conn:
            for name in ('023_account_emails.sql', '026_hiring_access.sql', '028_workspace_invitation_mail.sql'):
                sql = (Path(__file__).parents[1] / 'migrations' / name).read_text()
                conn.exec_driver_sql(sql)
                conn.exec_driver_sql(sql)
        monkeypatch.setattr(database, 'engine', engine)
        monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
        yield
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


@pytest.fixture
def access_client(db, monkeypatch):
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'development')
    monkeypatch.delenv('AUTH_APP_CHECK_REQUIRED', raising=False)
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
    monkeypatch.setenv('FRONTEND_URL', 'https://cookcredit-hiring-staging.web.app')
    monkeypatch.setattr(auth, '_verify_token', lambda token: {
        'uid': token, 'email': access.OWNER_EMAIL if token == 'owner' else token,
        'email_verified': True})
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    app.register_blueprint(access_bp, url_prefix='/access')
    return app.test_client()


OWNER = {'Authorization':'Bearer owner'}


def test_request_approve_mail_revoke_and_no_public_reapproval(access_client, monkeypatch):
    client = access_client
    body = {'email':'Chef@Example.com', 'name':'Chef', 'company':'Kitchen', 'contactConsent':True}
    assert client.post('/access/requests', json=body).status_code == 202
    listed = client.get('/access/owner/requests', headers=OWNER)
    assert listed.status_code == 200
    row = listed.json['requests'][0]
    assert row['email'] == 'chef@example.com' and row['status'] == 'pending'
    assert not access.access_allowed(row['email'])
    url = '/access/owner/requests/'+row['id']+'/decision'
    approved = client.post(url, headers=OWNER, json={'action':'approve', 'revision':0, 'sendEmail':True})
    assert approved.status_code == 200
    assert access.access_allowed(row['email'])
    assert access.access_allowed(row['email'], legacy_setting='AUTH_EMAIL_TEST_RECIPIENTS')
    assert client.post(url, headers=OWNER, json={'action':'approve','revision':0,'sendEmail':True}).status_code == 409
    with db_session() as session:
        assert session.query(HiringAccessRequest).count() == 1
        assert session.query(AccountEmail).filter_by(kind='access_approved').count() == 1
        invite = session.query(AccountEmail).filter_by(kind='access_approved').one()
    sent = []
    monkeypatch.setattr(account_email, '_send_google_smtp', lambda *args: sent.append(args))
    assert account_email.deliver_access_email(invite) == 'sent'  # No Firebase account is needed yet.
    assert sent[0][0] == 'chef@example.com'
    assert 'https://cookcredit-hiring-staging.web.app/signup' in sent[0][2]
    assert client.post(url, headers=OWNER, json={'action':'revoke','revision':1}).status_code == 200
    monkeypatch.setenv('STAGING_ALLOWED_EMAILS', row['email'])
    assert not access.access_allowed(row['email'])  # Revocation overrides old configuration.
    assert account_email.deliver_access_email(invite) == 'skipped'
    assert client.post('/access/requests', json={**body,'name':'overwritten'}).status_code == 202
    with db_session() as session:
        saved = session.get(HiringAccessRequest, uuid.UUID(row['id']))
        assert saved.status == 'revoked' and saved.name == 'Chef'
        assert session.query(HiringAccessEvent).count() == 3


def test_approve_without_email_then_explicit_send(access_client):
    c = access_client
    row = c.post('/access/owner/requests', headers=OWNER, json={'email':'later@example.com'}).json['request']
    url = '/access/owner/requests/'+row['id']+'/decision'
    assert c.post(url, headers=OWNER, json={'action':'approve','revision':0,'sendEmail':False}).status_code == 200
    with db_session() as session:
        assert session.query(AccountEmail).count() == 0
    assert c.post(url, headers=OWNER, json={'action':'resend','revision':1}).status_code == 200
    with db_session() as session:
        assert session.query(AccountEmail).filter_by(kind='access_approved').count() == 1


def test_public_request_cannot_remove_existing_tester_access(access_client, monkeypatch):
    monkeypatch.setenv('STAGING_ALLOWED_EMAILS', 'existing@example.com')
    monkeypatch.setenv('AUTH_EMAIL_TEST_RECIPIENTS', 'existing@example.com')
    assert access.access_allowed('existing@example.com')
    assert access_client.post('/access/requests', json={
        'email': 'existing@example.com', 'contactConsent': True}).status_code == 202
    assert access.access_allowed('existing@example.com')
    assert access.access_allowed('existing@example.com', legacy_setting='AUTH_EMAIL_TEST_RECIPIENTS')
    with db_session() as session:
        row = session.query(HiringAccessRequest).filter_by(email='existing@example.com').one()
        access.decide(session, row, action='decline', revision=0, actor_id='owner', send_email=False)
    assert not access.access_allowed('existing@example.com')


def test_concurrent_requests_create_one_pending_request_and_notification(access_client):
    def submit(_):
        with db_session() as session:
            row, created = access.create_request(session, {'email':'parallel@example.com'}, source='website')
            return created
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(submit, range(8))) == 1
    with db_session() as session:
        assert session.query(HiringAccessRequest).count() == 1
        assert session.query(AccountEmail).filter_by(kind='access_requested').count() == 1


def test_concurrent_owner_decisions_queue_only_one_invitation(access_client):
    row = access_client.post('/access/owner/requests', headers=OWNER,
                             json={'email': 'decision@example.com'}).json['request']
    app = access_client.application
    def approve(_):
        with app.test_client() as client:
            return client.post('/access/owner/requests/' + row['id'] + '/decision',
                headers=OWNER, json={'action': 'approve', 'revision': 0,
                                     'sendEmail': True}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve, range(2))) == [200, 409]
    with db_session() as session:
        assert session.query(AccountEmail).filter_by(kind='access_approved').count() == 1
        assert session.get(HiringAccessRequest, uuid.UUID(row['id'])).revision == 1


def test_owner_only_pagination_has_no_missing_or_duplicate_requests(access_client):
    with db_session() as session:
        for i in range(53):
            access.create_request(session, {'email':f'page{i}@example.com'}, source='owner')
    first = access_client.get('/access/owner/requests', headers=OWNER).json
    second = access_client.get('/access/owner/requests?cursor='+first['nextCursor'], headers=OWNER).json
    assert len(first['requests']) == 50 and len(second['requests']) == 3
    assert len({r['id'] for r in first['requests']+second['requests']}) == 53
    assert not second['nextCursor']
    assert access_client.get('/access/owner/requests', headers={'Authorization':'Bearer page0@example.com'}).status_code == 403


@pytest.mark.parametrize('contact_fails', [False, True])
def test_two_inboxes_have_independent_checkpoints_and_deduplicate(access_client, monkeypatch, contact_fails):
    from services import hiring_access_inbox as importer
    from models.hiring_access import HiringAccessInbox
    monkeypatch.setenv('HIRING_ACCESS_INBOX_ENABLED', '1')
    for _, key in importer.MAILBOXES:
        monkeypatch.setenv(key, 'test-only')
    reads = []
    class Mailbox:
        def login(self, address, password):
            self.address = address
            assert password == 'test-only'
            if contact_fails and address == importer.CONTACT:
                raise RuntimeError('simulated unavailable inbox')
        def select(self, folder, readonly):
            assert folder == 'INBOX' and readonly is True
            return 'OK', []
        def response(self, key):
            assert key == 'UIDVALIDITY'
            return key, [b'1']
        def uid(self, command, *args):
            uid = 10 if self.address == importer.CONTACT else 20
            if command == 'search':
                return 'OK', [str(uid).encode()]
            assert command == 'fetch' and 'BODY.PEEK' in args[1]
            reads.append((self.address, args[0]))
            return 'OK', [(b'header', (
                'From: Chef <same@example.com>\r\nTo: ' + self.address +
                '\r\nSubject: hiring access\r\n\r\n').encode())]
        def logout(self):
            pass
    connect = lambda *args, **kwargs: Mailbox()
    result = importer.sync_hiring_inbox(connect=connect)
    assert result['imported'] == 1 and result['failed'] == contact_fails
    assert importer.sync_hiring_inbox(connect=connect)['imported'] == 0
    assert len(reads) == (1 if contact_fails else 2)
    with db_session() as session:
        assert session.query(HiringAccessRequest).one().status == 'pending'
        assert session.query(AccountEmail).filter_by(kind='access_requested').count() == 1
        assert session.query(AccountEmail).filter_by(kind='access_approved').count() == 0
        contact = session.get(HiringAccessInbox, importer.CONTACT)
        owner = session.get(HiringAccessInbox, access.OWNER_EMAIL)
        assert contact.last_uid == (0 if contact_fails else 10)
        assert bool(contact.last_error) == contact_fails
        assert owner.last_uid == 20 and owner.last_error is None


def test_unverified_approved_user_can_request_verification_but_cannot_read_workspace(access_client, monkeypatch):
    from routes.auth import auth_bp
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('AUTH_EMAILS_ENABLED', '1')
    monkeypatch.setenv('AUTH_APP_CHECK_REQUIRED', '1')
    monkeypatch.setenv('FIREBASE_APP_CHECK_APP_IDS', 'test-app')
    from middleware import app_check
    from firebase_admin import app_check as provider_check
    monkeypatch.setattr(app_check, 'get_auth', lambda: None)
    monkeypatch.setattr(provider_check, 'verify_token', lambda _: {'app_id':'test-app'})
    with db_session() as session:
        row, _ = access.create_request(session, {'email':'new@example.com'}, source='owner')
        access.decide(session, row, action='approve', revision=0, actor_id='owner', send_email=False)
    monkeypatch.setattr(auth, '_verify_token', lambda _: {'uid':'new', 'email':'new@example.com','email_verified':False})
    app = Flask(__name__)
    app.config.update(TESTING=True,RATELIMIT_ENABLED=False)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    headers = {'Authorization':'Bearer new','X-Firebase-AppCheck':'valid'}
    assert app.test_client().post('/auth/email/verification', headers=headers).status_code == 202
    assert app.test_client().post('/auth/complete-verification', headers=headers).status_code == 403
    with db_session() as session:
        assert session.query(AccountEmail).filter_by(kind='verify', recipient='new@example.com').count() == 1
