import pytest
from cryptography.fernet import Fernet

from services.runtime_config import validate_runtime_configuration


def _production(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.setenv('FRONTEND_URL', 'https://app.example.test')
    monkeypatch.setenv('PUBLIC_API_URL', 'https://api.example.test')
    monkeypatch.setenv('ASSESSMENT_PUBLIC_URL', 'https://assessment.example.test/')
    monkeypatch.setenv('INTERNAL_SECRET', 'i' * 32)


def test_local_runtime_configuration_is_permissive(monkeypatch):
    monkeypatch.delenv('FLASK_ENV', raising=False)
    monkeypatch.delenv('K_SERVICE', raising=False)
    validate_runtime_configuration()


def test_native_account_email_requires_no_sendgrid_secret(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setenv('AUTH_EMAILS_ENABLED', '1')
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'firebase')
    monkeypatch.setenv('AUTH_APP_CHECK_REQUIRED', '1')
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'test-project')
    monkeypatch.setenv('FIREBASE_APP_CHECK_APP_IDS', 'test-app')
    monkeypatch.delenv('SENDGRID_API_KEY', raising=False)
    monkeypatch.delenv('SENDGRID_FROM_EMAIL', raising=False)
    validate_runtime_configuration()
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '1')
    with pytest.raises(RuntimeError, match='SENDGRID_API_KEY'):
        validate_runtime_configuration()


def test_google_smtp_requires_mailbox_secret_and_staging_recipient_limit(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('STAGING_ALLOWED_EMAILS', 'owner@cookcredit.com')
    monkeypatch.setenv('AUTH_EMAILS_ENABLED', '1')
    monkeypatch.setenv('AUTH_WELCOME_EMAILS_ENABLED', '1')
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER', 'google_smtp')
    monkeypatch.setenv('AUTH_APP_CHECK_REQUIRED', '1')
    monkeypatch.setenv('FIREBASE_PROJECT_ID', 'test-project')
    monkeypatch.setenv('FIREBASE_APP_CHECK_APP_IDS', 'test-app')
    monkeypatch.setenv('GOOGLE_SMTP_USER', 'owner@cookcredit.com')
    monkeypatch.delenv('GOOGLE_SMTP_APP_PASSWORD', raising=False)
    monkeypatch.delenv('AUTH_EMAIL_TEST_RECIPIENTS', raising=False)
    monkeypatch.delenv('SENDGRID_API_KEY', raising=False)
    with pytest.raises(RuntimeError, match='GOOGLE_SMTP_APP_PASSWORD'):
        validate_runtime_configuration()
    monkeypatch.setenv('GOOGLE_SMTP_APP_PASSWORD', 'test-only')
    with pytest.raises(RuntimeError, match='AUTH_EMAIL_TEST_RECIPIENTS'):
        validate_runtime_configuration()
    monkeypatch.setenv('AUTH_EMAIL_TEST_RECIPIENTS', 'owner@cookcredit.com')
    validate_runtime_configuration()
    monkeypatch.setenv('GOOGLE_SMTP_USER', 'owner@outside.test')
    with pytest.raises(RuntimeError, match='CookCredit mailbox'):
        validate_runtime_configuration()


def test_production_reports_all_missing_core_settings(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    for key in ('FRONTEND_URL', 'PUBLIC_API_URL', 'ASSESSMENT_PUBLIC_URL', 'INTERNAL_SECRET'):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match='ASSESSMENT_PUBLIC_URL'):
        validate_runtime_configuration()


def test_enabled_production_features_require_shared_and_provider_secrets(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setenv('PARTNER_INTEGRATIONS_ENABLED', '1')
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '1')
    monkeypatch.setenv('BEAM_AGENT_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_EXPECT_MULTI_INSTANCE', '1')
    monkeypatch.setenv('MARKET', 'US')
    for key in ('WEBHOOK_SECRET_ENCRYPTION_KEY', 'PARTNER_API_KEY_PEPPER', 'STRIPE_SECRET_KEY',
                'STRIPE_WEBHOOK_SECRET', 'STRIPE_TEAM_PRICE_ID', 'STRIPE_INTEGRATION_PRICE_ID',
                'GEMINI_API_KEY', 'REDIS_URL'):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError) as caught:
        validate_runtime_configuration()
    message = str(caught.value)
    assert ('GEMINI_API_KEY' in message and 'REDIS_URL' in message
            and 'STRIPE_TEAM_PRICE_ID' in message and 'STRIPE_INTEGRATION_PRICE_ID' in message)


def test_complete_production_configuration_passes(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setenv('PARTNER_INTEGRATIONS_ENABLED', '1')
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '1')
    monkeypatch.setenv('BEAM_AGENT_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_EXPECT_MULTI_INSTANCE', '1')
    monkeypatch.setenv('MARKET', 'US')
    monkeypatch.setenv('WEBHOOK_SECRET_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('PARTNER_API_KEY_PEPPER', 'p' * 32)
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_value')
    monkeypatch.setenv('STRIPE_WEBHOOK_SECRET', 'whsec_value')
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    monkeypatch.setenv('STRIPE_INTEGRATION_PRICE_ID', 'price_integration')
    monkeypatch.setenv('GEMINI_API_KEY', 'gemini-key')
    monkeypatch.setenv('REDIS_URL', 'rediss://redis.example.test:6379/0')
    validate_runtime_configuration()


def test_location_requires_server_credentials_in_cloud(monkeypatch):
    _production(monkeypatch)
    monkeypatch.setenv('LOCATION_SEARCH_ENABLED', '1')
    monkeypatch.delenv('GOOGLE_GEOCODING_API_KEY', raising=False)
    monkeypatch.delenv('LOCATION_TOKEN_SECRET', raising=False)
    with pytest.raises(RuntimeError, match='GOOGLE_GEOCODING_API_KEY'):
        validate_runtime_configuration()
    monkeypatch.setenv('GOOGLE_GEOCODING_API_KEY', 'test-key')
    monkeypatch.setenv('LOCATION_TOKEN_SECRET', 'too-short')
    with pytest.raises(RuntimeError, match='LOCATION_TOKEN_SECRET'):
        validate_runtime_configuration()
    monkeypatch.setenv('LOCATION_TOKEN_SECRET', 'l' * 32)
    validate_runtime_configuration()
