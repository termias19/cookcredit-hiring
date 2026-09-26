"""Fail closed when a production process is missing launch-critical configuration."""
import os
from urllib.parse import urlsplit


def _enabled(name, default='0'):
    return os.environ.get(name, default).strip() == '1'


def deployment_environment():
    default = 'production' if os.environ.get('K_SERVICE') or os.environ.get('FLASK_ENV') == 'production' else 'development'
    value = os.environ.get('COOKCREDIT_ENVIRONMENT', default)
    if value not in ('development', 'staging', 'production'):
        raise RuntimeError('COOKCREDIT_ENVIRONMENT must be development, staging, or production')
    return value


def _https_origin(name, *, allow_path=False):
    raw = os.environ.get(name, '').split(',', 1)[0].strip()
    parsed = urlsplit(raw)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or (not allow_path and parsed.path not in ('', '/'))):
        raise RuntimeError(f'{name} must be an absolute HTTPS URL')


def validate_runtime_configuration():
    """Validate shape and presence before Cloud Run begins accepting requests.

    Local development and tests remain intentionally permissive. Feature flags make
    optional subsystems explicit; deployment config enables every shipped subsystem.
    """
    environment = deployment_environment()
    if environment == 'development' and os.environ.get('FLASK_ENV') != 'production' and not os.environ.get('K_SERVICE'):
        return

    required = ['FRONTEND_URL', 'PUBLIC_API_URL', 'ASSESSMENT_PUBLIC_URL', 'INTERNAL_SECRET']
    if _enabled('HIRING_ACCESS_APPROVALS_ENABLED'):
        if (not _enabled('AUTH_EMAILS_ENABLED') or os.getenv('AUTH_EMAIL_PROVIDER') != 'google_smtp'):
            raise RuntimeError('Hiring approvals require the working Google account email provider')
    if _enabled('HIRING_ACCESS_INBOX_ENABLED'):
        if not _enabled('HIRING_ACCESS_APPROVALS_ENABLED'):
            raise RuntimeError('Inbox import requires hiring approvals')
        required += ['HIRING_INBOX_CONTACT_APP_PASSWORD', 'HIRING_INBOX_OWNER_APP_PASSWORD']
    if _enabled('INTEGRATION_EARLY_ACCESS_ENABLED') and os.environ.get('BUSINESS_BILLING_ENABLED') != '0':
        raise RuntimeError('Free integration access requires billing to be explicitly disabled')
    if environment == 'staging':
        required += ['STAGING_ALLOWED_EMAILS']
    if _enabled('PARTNER_INTEGRATIONS_ENABLED'):
        required += ['WEBHOOK_SECRET_ENCRYPTION_KEY', 'PARTNER_API_KEY_PEPPER']
    if _enabled('BUSINESS_BILLING_ENABLED') and os.environ.get('MARKET', 'US').upper() == 'US':
        required += ['STRIPE_SECRET_KEY', 'STRIPE_WEBHOOK_SECRET', 'STRIPE_TEAM_PRICE_ID',
                     'STRIPE_INTEGRATION_PRICE_ID']
    provider = os.environ.get('AUTH_EMAIL_PROVIDER', 'firebase')
    if _enabled('AUTH_EMAILS_ENABLED') or _enabled('AUTH_WELCOME_EMAILS_ENABLED'):
        if provider not in ('firebase', 'sendgrid', 'google_smtp'):
            raise RuntimeError('AUTH_EMAIL_PROVIDER must be firebase, sendgrid or google_smtp')
        required += ['FIREBASE_PROJECT_ID', 'FIREBASE_APP_CHECK_APP_IDS']
        if provider == 'sendgrid':
            required += ['SENDGRID_API_KEY', 'SENDGRID_FROM_EMAIL']
        if provider == 'google_smtp':
            required += ['GOOGLE_SMTP_USER', 'GOOGLE_SMTP_APP_PASSWORD']
            sender = os.environ.get('GOOGLE_SMTP_USER', '')
            if sender and (not sender.endswith('@cookcredit.com') or any(c.isspace() for c in sender)
                           or sender.count('@') != 1 or sender.startswith('@')):
                raise RuntimeError('GOOGLE_SMTP_USER must be a CookCredit mailbox')
        if not _enabled('AUTH_APP_CHECK_REQUIRED'):
            raise RuntimeError('Account email requires Firebase App Check enforcement')
        if environment == 'staging' and provider in ('sendgrid', 'google_smtp'):
            required += ['AUTH_EMAIL_TEST_RECIPIENTS']
    if _enabled('AUTH_WELCOME_EMAILS_ENABLED') and provider == 'firebase':
        # Legacy optional SendGrid welcome delivery alongside native Auth email.
        required += ['SENDGRID_API_KEY', 'SENDGRID_FROM_EMAIL']
        if environment == 'staging':
            required += ['AUTH_EMAIL_TEST_RECIPIENTS']
    if _enabled('BEAM_AGENT_ENABLED'):
        required += ['GEMINI_API_KEY']
    if _enabled('LOCATION_SEARCH_ENABLED'):
        required += ['GOOGLE_GEOCODING_API_KEY', 'LOCATION_TOKEN_SECRET']
    if _enabled('COOKCREDIT_EXPECT_MULTI_INSTANCE'):
        required += ['REDIS_URL']
    missing = sorted({key for key in required if not os.environ.get(key, '').strip()})
    if missing:
        raise RuntimeError('Missing production settings: ' + ', '.join(missing))
    if (environment == 'staging' and _enabled('BUSINESS_BILLING_ENABLED')
            and not os.environ.get('STRIPE_SECRET_KEY', '').startswith(('sk_test_', 'rk_test_'))):
        raise RuntimeError('Staging billing requires a Stripe test-mode key')

    _https_origin('FRONTEND_URL')
    _https_origin('PUBLIC_API_URL')
    _https_origin('ASSESSMENT_PUBLIC_URL', allow_path=True)
    for name in ('INTERNAL_SECRET', 'PARTNER_API_KEY_PEPPER', 'LOCATION_TOKEN_SECRET'):
        value = os.environ.get(name, '')
        if value and len(value) < 32:
            raise RuntimeError(f'{name} must contain at least 32 characters')
    redis_url = os.environ.get('REDIS_URL', '')
    if redis_url and urlsplit(redis_url).scheme not in ('redis', 'rediss'):
        raise RuntimeError('REDIS_URL must use redis:// or rediss://')
    if _enabled('PARTNER_INTEGRATIONS_ENABLED'):
        try:
            from cryptography.fernet import Fernet
            Fernet(os.environ['WEBHOOK_SECRET_ENCRYPTION_KEY'].encode())
        except (ValueError, TypeError) as exc:
            raise RuntimeError('WEBHOOK_SECRET_ENCRYPTION_KEY must be a valid Fernet key') from exc
