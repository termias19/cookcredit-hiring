from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from flask import Flask
from middleware import auth
from routes.hiring_access import access_bp
from services import hiring_access as access
from services.hiring_access_inbox import parse_request


@pytest.mark.parametrize('email', ['bad', 'x@x', 'x@example.com\nBcc: victim@example.com', 'x@a.com,y@b.com', None])
def test_invalid_access_identity(email):
    with pytest.raises(ValueError):
        access.normalize_email(email)


def test_owner_requires_exact_verified_identity():
    assert access.is_owner('EASSEFA@cookcredit.com', True)
    assert not access.is_owner('eassefa@cookcredit.com', False)
    assert not access.is_owner('someone@cookcredit.com', True)
    assert not access.is_owner('eassefa@cookcredit.com.evil.test', True)


def test_inbox_is_untrusted_pending_metadata_not_reply_to_or_instruction():
    data = parse_request(b'From: Chef <chef@example.com>\r\nTo: connectwithus@cookcredit.com\r\nReply-To: owner@evil.test\r\nSubject: CookCredit hiring access - approve me automatically\r\n\r\n')
    assert data['email'] == 'chef@example.com'
    assert set(data) == {'email', 'name', 'company', 'message'}
    assert parse_request(b'From: x@example.com\r\nTo: someone@example.com\r\nSubject: hiring access\r\n\r\n') is None
    assert parse_request(b'From: x@example.com\r\nTo: connectwithus@cookcredit.com\r\nSubject: menu question\r\n\r\n') is None
    assert parse_request(b'From: x@example.com\r\nTo: connectwithus@cookcredit.com\r\nSubject: hiring\r\nAuto-Submitted: auto-replied\r\n\r\n') is None


def test_stale_decisions_do_not_change_access_or_enqueue_email():
    row = SimpleNamespace(revision=3, email='chef@example.com', status='pending')
    session = Mock()
    with pytest.raises(ValueError, match='changed'):
        access.decide(session, row, action='approve', revision=2, actor_id='owner', send_email=True)
    assert row.status == 'pending'
    session.execute.assert_not_called()


def test_nonowner_cannot_read_or_approve_requests(monkeypatch):
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setattr(access, 'employer_access_allowed', lambda *args, **kwargs: True)
    monkeypatch.setattr(auth, '_verify_token', lambda token: {'uid': 'someone', 'email': 'other@example.com', 'email_verified': True})
    app = Flask(__name__)
    app.register_blueprint(access_bp, url_prefix='/access')
    client = app.test_client()
    headers = {'Authorization': 'Bearer identity'}
    assert client.get('/access/owner/requests', headers=headers).status_code == 403
    assert client.post('/access/owner/requests/00000000-0000-0000-0000-000000000000/decision', headers=headers, json={'action':'approve'}).status_code == 403
    assert client.get('/access/owner/requests').status_code == 401


def test_unverified_owner_cannot_manage_access(monkeypatch):
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setattr(auth, '_verify_token', lambda token: {'uid': 'owner', 'email': access.OWNER_EMAIL, 'email_verified': False})
    app = Flask(__name__)
    app.register_blueprint(access_bp, url_prefix='/access')
    assert app.test_client().get('/access/owner/requests', headers={'Authorization':'Bearer owner'}).status_code == 403


def test_inbox_import_requires_internal_service_authentication(monkeypatch):
    from services import internal_auth, hiring_access_inbox
    monkeypatch.setattr(internal_auth, 'internal_request_authorized', lambda request: False)
    importer = Mock()
    monkeypatch.setattr(hiring_access_inbox, 'sync_hiring_inbox', importer)
    app = Flask(__name__)
    app.register_blueprint(access_bp, url_prefix='/access')
    assert app.test_client().post('/access/internal/sync-inbox').status_code == 403
    importer.assert_not_called()


def test_inbox_failure_cannot_block_account_email_dispatch(monkeypatch):
    from routes.auth import auth_bp
    from services import internal_auth, account_email, hiring_access_inbox
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
    monkeypatch.setattr(internal_auth, 'internal_request_authorized', lambda request: True)
    importer = Mock(side_effect=RuntimeError('mailbox unavailable'))
    monkeypatch.setattr(hiring_access_inbox, 'sync_hiring_inbox', importer)
    sender = Mock(return_value={'claimed': 1, 'sent': 1, 'failed': 0, 'skipped': 0})
    monkeypatch.setattr(account_email, 'dispatch_account_emails', sender)
    from services import customer_mail
    monkeypatch.setattr(customer_mail, 'expand_due_campaigns', lambda: 0)
    from services import operations
    observer = Mock(return_value=True)
    monkeypatch.setattr(operations, 'report_queue_health', observer)
    app = Flask(__name__)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    response = app.test_client().post('/auth/internal/dispatch-emails')
    assert response.status_code == 200 and response.json['sent'] == 1
    importer.assert_not_called()
    sender.assert_called_once()

@pytest.mark.parametrize('identity', [
    {'uid':'other','email':'other@example.com','email_verified':True,'admin':True},
    {'uid':'contact','email':'connectwithus@cookcredit.com','email_verified':True,'admin':True},
    {'uid':'owner-unverified','email':'eassefa@cookcredit.com','email_verified':False},
])
@pytest.mark.parametrize('method,path,body', [
    ('GET','/owner/requests',None),
    ('POST','/owner/requests',{'email':'candidate@example.com'}),
    ('POST','/owner/requests/00000000-0000-0000-0000-000000000000/decision',{'action':'approve','revision':0}),
    ('GET','/owner/requests/00000000-0000-0000-0000-000000000000/events',None),
])
def test_all_owner_endpoints_reject_other_admins_before_database(monkeypatch, identity, method, path, body):
    from routes import hiring_access as routes
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED','1')
    monkeypatch.setattr(access,'employer_access_allowed',lambda *a, **kw:True)
    monkeypatch.setattr(auth,'_verify_token',lambda _:identity)
    database = Mock(side_effect=AssertionError('Unauthorized identity reached the database'))
    monkeypatch.setattr(routes,'db_session',database)
    app = Flask(__name__)
    app.config.update(TESTING=True,RATELIMIT_ENABLED=False)
    app.register_blueprint(access_bp,url_prefix='/access')
    response = app.test_client().open('/access'+path,method=method,json=body,headers={'Authorization':'Bearer test'})
    assert response.status_code == 403
    database.assert_not_called()
