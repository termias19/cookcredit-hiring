"""Cloud-only boundaries must fail closed without affecting local development."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask, g
from middleware import auth
from services.readiness import readiness
from services import storage_signing


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config['TESTING'] = True

    @app.get('/protected')
    @auth.require_auth
    def protected():
        return {'uid': g.user_id}

    app.add_url_rule('/bootstrap', 'auth.sync_user', auth.require_auth(lambda: {'created': True}), methods=['POST'])
    app.add_url_rule('/own-profile', 'auth.get_me', auth.require_auth(lambda: {'uid': g.user_id}), methods=['GET'])

    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('STAGING_ALLOWED_EMAILS', 'Invited@example.test')
    monkeypatch.setattr(auth, '_verify_token', lambda token: {
        'uid': 'test-user', 'email': token, 'email_verified': True})
    return app.test_client()


def test_staging_rejects_uninvited_verified_identity(client):
    rejected = client.get('/protected', headers={'Authorization': 'Bearer other@example.test'})
    assert rejected.status_code == 403
    assert rejected.json['code'] == 'staging_access_denied'
    assert client.get('/protected', headers={'Authorization': 'Bearer invited@example.test'}).status_code == 200


def test_staging_cannot_claim_invited_email_without_verification(client, monkeypatch):
    monkeypatch.setattr(auth, '_verify_token', lambda _: {
        'uid': 'test-user', 'email': 'invited@example.test', 'email_verified': False})
    assert client.get('/protected', headers={'Authorization': 'Bearer test'}).json['code'] == 'email_unverified'


def test_invited_unverified_signup_can_bootstrap_but_not_use_protected_actions(client, monkeypatch):
    monkeypatch.setattr(auth, '_verify_token', lambda _: {
        'uid': 'test-user', 'email': 'invited@example.test', 'email_verified': False})
    headers = {'Authorization': 'Bearer test'}
    assert client.post('/bootstrap', headers=headers).status_code == 200
    assert client.get('/own-profile', headers=headers).status_code == 200
    assert client.get('/protected', headers=headers).status_code == 403


def test_bootstrap_exception_does_not_bypass_staging_invitation(client):
    headers = {'Authorization': 'Bearer stranger@example.test'}
    assert client.post('/bootstrap', headers=headers).status_code == 403
    assert client.get('/own-profile', headers=headers).status_code == 403


def test_staging_fails_closed_if_allowlist_is_missing(client, monkeypatch):
    monkeypatch.delenv('STAGING_ALLOWED_EMAILS')
    assert client.get('/protected', headers={'Authorization': 'Bearer invited@example.test'}).status_code == 503


def test_production_does_not_apply_staging_allowlist(client, monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'production')
    assert client.get('/protected', headers={'Authorization': 'Bearer other@example.test'}).status_code == 200


@pytest.mark.parametrize('database_ok,redis_ok', [(False, True), (True, False), (False, False), (True, True)])
def test_readiness_requires_both_cloud_dependencies(monkeypatch, database_ok, redis_ok):
    monkeypatch.setenv('COOKCREDIT_EXPECT_MULTI_INSTANCE', '1')
    checks, ok = readiness(lambda: database_ok, SimpleNamespace(check=lambda: redis_ok))
    assert checks == {'database': database_ok, 'rateLimits': redis_ok}
    assert ok == (database_ok and redis_ok)


def test_readiness_handles_dependency_exceptions(monkeypatch):
    monkeypatch.setenv('COOKCREDIT_EXPECT_MULTI_INSTANCE', '1')
    def offline():
        raise ConnectionError('offline')
    checks, ok = readiness(offline, SimpleNamespace(check=offline))
    assert not ok and not any(checks.values())


def test_cloud_signing_refreshes_adc_and_uses_named_iam_identity(monkeypatch):
    monkeypatch.setenv('FIREBASE_USE_ADC', '1')
    monkeypatch.setenv('STORAGE_SIGNING_SERVICE_ACCOUNT', 'runtime@staging.iam.gserviceaccount.com')
    credentials = SimpleNamespace(valid=False, token=None)
    def refresh(_request):
        credentials.token = 'ephemeral-test-token'
    credentials.refresh = Mock(side_effect=refresh)
    monkeypatch.setattr(storage_signing.google.auth, 'default', lambda **_: (credentials, 'staging'))
    blob = SimpleNamespace(generate_signed_url=Mock(return_value='https://storage.example.test/signed'))
    assert storage_signing.signed_url(blob, method='PUT', version='v4') == 'https://storage.example.test/signed'
    credentials.refresh.assert_called_once()
    args = blob.generate_signed_url.call_args.kwargs
    assert args['service_account_email'] == 'runtime@staging.iam.gserviceaccount.com'
    assert args['access_token'] == 'ephemeral-test-token'
    assert args['method'] == 'PUT'


def test_cloud_signing_requires_identity(monkeypatch):
    monkeypatch.setenv('FIREBASE_USE_ADC', '1')
    monkeypatch.delenv('STORAGE_SIGNING_SERVICE_ACCOUNT', raising=False)
    with pytest.raises(RuntimeError, match='identity'):
        storage_signing.signed_url(object())


def test_explicitly_disabled_billing_stops_provider_calls(monkeypatch):
    from routes.stripe import stripe_bp
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    app = Flask(__name__)
    app.register_blueprint(stripe_bp, url_prefix='/stripe')
    response = app.test_client().post('/stripe/business/checkout', json={})
    assert response.status_code == 503
    assert response.json['code'] == 'billing_unavailable'


def test_disabled_assessment_bridge_does_not_create_session(monkeypatch):
    from routes.hiring import hiring_bp
    monkeypatch.setenv('ASSESSMENT_BRIDGE_ENABLED', '0')
    monkeypatch.setattr(auth, '_verify_token', lambda _: {'uid': 'tester', 'email': 'test@example.test', 'email_verified': True})
    app = Flask(__name__)
    app.register_blueprint(hiring_bp, url_prefix='/hiring')
    response = app.test_client().post('/hiring/applications/not-a-record/attempts/start',
                                      headers={'Authorization': 'Bearer test'})
    assert response.status_code == 503
    assert response.json['code'] == 'assessment_unavailable'


@pytest.mark.parametrize('endpoint,method,verified,expected', [
    ('auth.sync_user', 'POST', False, 200),
    ('auth.get_me', 'GET', False, 200),
    ('auth.request_verification_email', 'POST', False, 200),
    ('auth.request_verification_email', 'GET', False, 403),
    ('auth.update_me', 'PATCH', False, 403),
    ('auth.complete_verification', 'POST', False, 403),
    ('auth.complete_verification', 'POST', True, 200),
    ('hiring.apply', 'POST', False, 403),
    ('hiring.apply', 'POST', True, 200),
    ('hiring.get_application', 'GET', True, 200),
    ('hiring.start_attempt', 'POST', True, 200),
    ('hiring.complete_attempt', 'POST', True, 200),
    ('hiring.application_cv', 'GET', True, 200),
    ('business.candidates', 'GET', True, 403),
    ('business.create_role', 'POST', True, 403),
    ('owner.approve', 'POST', True, 403),
])
def test_public_applicant_boundary(monkeypatch, endpoint, method, verified, expected):
    from services import hiring_access
    monkeypatch.setattr(hiring_access, 'enabled', lambda: True)
    monkeypatch.setattr(hiring_access, 'access_allowed', lambda email: False)
    monkeypatch.setattr(auth, '_verify_token', lambda _: {
        'uid': 'applicant', 'email': 'applicant@example.test', 'email_verified': verified})
    app = Flask(__name__)
    app.add_url_rule('/action', endpoint, auth.require_auth(lambda: {'ok': True}), methods=[method])
    response = app.test_client().open('/action', method=method, headers={'Authorization': 'Bearer test'})
    assert response.status_code == expected
    assert app.test_client().open('/action', method=method).status_code == 401
