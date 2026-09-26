from contextlib import contextmanager
from types import SimpleNamespace
from flask import Flask
import pytest
from middleware import auth as auth_middleware
from routes import auth
from services import account_email


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'development')
    monkeypatch.setenv('AUTH_EMAILS_ENABLED', '1')
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'sendgrid')
    monkeypatch.delenv('AUTH_APP_CHECK_REQUIRED', raising=False)
    monkeypatch.setattr(auth_middleware, '_verify_token', lambda _: {'uid': 'customer', 'email': 'customer@example.test', 'email_verified': False})
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    app.register_blueprint(auth.auth_bp, url_prefix='/auth')
    @contextmanager
    def session():
        yield object()
    monkeypatch.setattr(auth, 'db_session', session)
    return app.test_client()


def test_verification_cannot_send_to_another_address(client, monkeypatch):
    calls = []
    monkeypatch.setattr(account_email, 'enqueue_account_email', lambda *a, **kw: calls.append(kw))
    response = client.post('/auth/email/verification', json={'email': 'victim@example.test'}, headers={'Authorization': 'Bearer token'})
    assert response.status_code == 202
    assert calls == [{'kind': 'verify', 'recipient': 'customer@example.test', 'user_id': 'customer'}]


def test_reset_never_discloses_account_existence(client, monkeypatch):
    calls = []
    monkeypatch.setattr(account_email, 'enqueue_account_email', lambda *a, **kw: calls.append(kw))
    first = client.post('/auth/email/password-reset', json={'email': 'known@example.test'})
    second = client.post('/auth/email/password-reset', json={'email': 'absent@example.test'})
    assert first.status_code == second.status_code == 202
    assert first.json == second.json
    assert len(calls) == 2
    assert client.post('/auth/email/password-reset', json=[]).status_code == 400


def test_welcome_requires_verified_token(client):
    assert client.post('/auth/complete-verification', headers={'Authorization': 'Bearer token'}).status_code == 403
    assert client.post('/auth/internal/dispatch-emails').status_code == 403


def test_staging_account_requests_fail_closed_without_attestation(client, monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    assert client.post('/auth/email/password-reset', json={'email': 'customer@example.test'}).status_code == 503
    monkeypatch.setenv('AUTH_APP_CHECK_REQUIRED', '1')
    monkeypatch.setenv('FIREBASE_APP_CHECK_APP_IDS', 'expected-web-app')
    assert client.post('/auth/email/password-reset', json={'email': 'customer@example.test'}).status_code == 403


def test_staging_email_allowlist_prevents_delivery(monkeypatch):
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '0')
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('AUTH_EMAIL_TEST_RECIPIENTS', 'approved@example.test')
    monkeypatch.setattr(account_email, 'get_auth', lambda: pytest.fail('No provider call allowed'))
    assert account_email.deliver_account_email(SimpleNamespace(recipient='other@example.test', kind='welcome')) == 'skipped'


@pytest.mark.parametrize('kind', ['verify', 'reset', 'welcome'])
def test_public_applicants_receive_account_mail_without_employer_approval(monkeypatch, kind):
    from services import hiring_access
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '1')
    monkeypatch.setenv('FRONTEND_URL', 'https://cookcredit-hiring-staging.web.app')
    monkeypatch.setenv('AUTH_EMAIL_TEST_RECIPIENTS', '')
    monkeypatch.setattr(hiring_access, 'access_allowed', lambda *a, **kw: pytest.fail('Account mail must not require employer approval'))
    user = SimpleNamespace(email='applicant@example.test', email_verified=kind != 'verify', disabled=False)
    monkeypatch.setattr(account_email, 'get_auth', lambda: SimpleNamespace(get_user=lambda _: user))
    monkeypatch.setattr(account_email, '_action_link', lambda *a: 'https://cookcredit.com/__/auth/action')
    sent = []
    monkeypatch.setattr(account_email, 'send_account_message', lambda *a: sent.append(a))
    assert account_email.deliver_account_email(SimpleNamespace(recipient=user.email, user_id='applicant', kind=kind)) == 'sent'
    assert len(sent) == 1 and sent[0][0] == user.email


@pytest.mark.parametrize('disabled,verified,recipient', [(True, False, 'applicant@example.test'), (False, True, 'applicant@example.test'), (False, False, 'other@example.test')])
def test_public_applicant_mail_still_checks_account_state(monkeypatch, disabled, verified, recipient):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
    user = SimpleNamespace(email='applicant@example.test', email_verified=verified, disabled=disabled)
    monkeypatch.setattr(account_email, 'get_auth', lambda: SimpleNamespace(get_user=lambda _: user))
    monkeypatch.setattr(account_email, 'send_account_message', lambda *a: pytest.fail('Must not send'))
    assert account_email.deliver_account_email(SimpleNamespace(recipient=recipient, user_id='applicant', kind='verify')) == 'skipped'


def test_email_branding_escaping_and_provider_failure(monkeypatch):
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'development')
    monkeypatch.setenv('SENDGRID_API_KEY', 'test-key')
    monkeypatch.setenv('SENDGRID_FROM_EMAIL', 'noreply@cookcredit.com')
    monkeypatch.setenv('FRONTEND_URL', 'https://app.example.test')
    user = SimpleNamespace(email='customer@example.test', email_verified=True, disabled=False)
    monkeypatch.setattr(account_email, 'get_auth', lambda: SimpleNamespace(get_user=lambda _: user))
    payloads = []
    def send(*args, **kwargs):
        payloads.append(kwargs)
        return SimpleNamespace(status_code=202)
    monkeypatch.setattr(account_email.requests, 'post', send)
    item = SimpleNamespace(recipient=user.email, user_id='customer', kind='welcome')
    assert account_email.deliver_account_email(item) == 'sent'
    payload = payloads[0]['json']
    assert payload['from'] == {'email': 'noreply@cookcredit.com', 'name': 'CookCredit'}
    assert payload['reply_to']['email'] == 'connectwithus@cookcredit.com'
    assert payload['tracking_settings']['click_tracking']['enable'] is False
    assert [part['type'] for part in payload['content']] == ['text/plain', 'text/html']
    _, _, markup = account_email.account_email_content('verify', 'https://app.example.test/?x="bad"&y=1')
    assert '&quot;bad&quot;&amp;y=1' in markup
    assert 'https://cookcredit.com/cookcredit-mark-orange.png' in markup
    assert 'https://cookcredit.com/privacy.html' in markup
    assert 'https://cookcredit.com/terms.html' in markup
    monkeypatch.setattr(account_email.requests, 'post', lambda *a, **kw: SimpleNamespace(status_code=401))
    with pytest.raises(RuntimeError, match='email_provider_unavailable'):
        account_email.deliver_account_email(item)


def test_native_provider_does_not_enqueue_sendgrid_messages(client, monkeypatch):
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'firebase')
    monkeypatch.setattr(account_email, 'enqueue_account_email', lambda *a, **kw: pytest.fail('No outbox fallback'))
    assert client.post('/auth/email/verification', headers={'Authorization': 'Bearer token'}).status_code == 503
    assert client.post('/auth/email/password-reset', json={'email': 'customer@example.test'}).status_code == 503


def test_native_verification_succeeds_without_welcome_provider(client, monkeypatch):
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'firebase')
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '0')
    monkeypatch.setattr(auth_middleware, '_verify_token', lambda _: {'uid': 'customer', 'email': 'customer@example.test', 'email_verified': True})
    monkeypatch.setattr(account_email, 'enqueue_account_email', lambda *a, **kw: pytest.fail('Welcome is disabled'))
    response = client.post('/auth/complete-verification', headers={'Authorization': 'Bearer token'})
    assert response.status_code == 200
    assert response.json == {'verified': True, 'welcomeEmail': 'disabled'}


def test_provider_switch_does_not_send_stale_jobs(monkeypatch):
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'firebase')
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '0')
    monkeypatch.setattr(account_email, 'get_auth', lambda: pytest.fail('No provider call'))
    for kind in ('verify', 'reset', 'welcome'):
        assert account_email.deliver_account_email(SimpleNamespace(kind=kind)) == 'skipped'


@pytest.mark.parametrize('kind', ['verify', 'reset', 'welcome'])
def test_google_smtp_sends_the_matching_branded_message(monkeypatch, kind):
    import ssl
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'development')
    monkeypatch.setenv('GOOGLE_SMTP_USER', 'sender@cookcredit.com')
    monkeypatch.setenv('GOOGLE_SMTP_APP_PASSWORD', 'abcd efgh ijkl mnop\n')
    monkeypatch.setenv('FRONTEND_URL', 'https://cookcredit.com')
    user = SimpleNamespace(email='customer@example.test', email_verified=kind != 'verify', disabled=False)
    monkeypatch.setattr(account_email, 'get_auth', lambda: SimpleNamespace(get_user=lambda _: user))
    monkeypatch.setattr(account_email, '_action_link', lambda action, _: 'https://cookcredit.com/__/auth/action?mode='+action)
    monkeypatch.setattr(account_email.requests, 'post', lambda *a, **kw: pytest.fail('Google must not call SendGrid'))
    calls = []
    class SMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ('smtp.gmail.com', 587, 15)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def ehlo(self): calls.append('ehlo')
        def starttls(self, context):
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
            calls.append('tls')
        def login(self, sender, password):
            assert sender == 'sender@cookcredit.com' and password == 'abcdefghijklmnop'
            assert calls == ['ehlo', 'tls', 'ehlo']
            calls.append('login')
        def send_message(self, message, from_addr, to_addrs):
            assert calls[-1] == 'login'
            assert from_addr == 'sender@cookcredit.com' and to_addrs == [user.email]
            assert str(message['From']) == 'CookCredit <sender@cookcredit.com>'
            assert str(message['Reply-To']) == 'CookCredit <connectwithus@cookcredit.com>'
            assert message.get_content_type() == 'multipart/alternative'
            text, markup = [part.get_content() for part in message.iter_parts()]
            assert 'privacy.html' in text and 'terms.html' in markup and 'cookcredit-mark-orange.png' in markup
            if kind == 'verify':
                assert 'verify your email' in str(message['Subject'])
                assert 'Confirm your email address' in text and 'Reset password' not in markup
            elif kind == 'reset':
                assert str(message['Subject']) == 'Reset your CookCredit password'
                assert 'Choose a new password' in text and 'Verify email' not in markup
            else:
                assert str(message['Subject']) == 'Your CookCredit account is ready'
                assert 'Welcome to CookCredit' in text and 'Your email address is verified' in text
            calls.append('sent')
            return {}
    monkeypatch.setattr(account_email.smtplib, 'SMTP', SMTP)
    assert account_email.deliver_account_email(SimpleNamespace(recipient=user.email, user_id='customer', kind=kind)) == 'sent'
    assert calls[-1] == 'sent'


def test_google_smtp_failure_does_not_expose_provider_details(monkeypatch):
    monkeypatch.setenv('GOOGLE_SMTP_USER', 'sender@cookcredit.com')
    monkeypatch.setenv('GOOGLE_SMTP_APP_PASSWORD', 'never-log-this')
    def fail(*args, **kwargs):
        raise account_email.smtplib.SMTPAuthenticationError(535, b'private provider details')
    monkeypatch.setattr(account_email.smtplib, 'SMTP', fail)
    with pytest.raises(RuntimeError, match='^email_provider_unavailable$'):
        account_email._send_google_smtp('customer@example.test', 'Subject', 'Text', '<p>Text</p>')


def test_google_provider_uses_protected_outbox_routes(client, monkeypatch):
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
    calls=[]
    monkeypatch.setattr(account_email, 'enqueue_account_email', lambda *a, **kw: calls.append(kw))
    assert client.post('/auth/email/verification', headers={'Authorization':'Bearer token'}).status_code == 202
    assert client.post('/auth/email/password-reset', json={'email':'customer@example.test'}).status_code == 202
    assert [call['kind'] for call in calls] == ['verify', 'reset']


def test_verification_link_stays_on_hiring_origin_with_issued_action_code(monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    monkeypatch.setenv('FRONTEND_URL','https://cookcredit-hiring-staging.web.app')
    provider=SimpleNamespace(ActionCodeSettings=lambda **kw: kw,
        generate_email_verification_link=lambda *a:'https://project.firebaseapp.com/__/auth/action?mode=verifyEmail&oobCode=test-code&apiKey=test-key&continueUrl=https%3A%2F%2Fcookcredit-hiring-staging.web.app%2Flogin')
    monkeypatch.setattr(account_email,'get_auth',lambda:provider)
    result=urlsplit(account_email._action_link('verify','candidate@example.test'))
    assert result.netloc=='cookcredit-hiring-staging.web.app'
    assert result.path=='/account/action'
    assert parse_qs(result.query)['oobCode']==['test-code']
