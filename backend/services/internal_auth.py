"""Authenticate scheduler/queue calls with a secret or a Google-issued OIDC token."""
import hmac
import os


def internal_request_authorized(request):
    expected = os.environ.get('INTERNAL_SECRET', '')
    supplied = request.headers.get('X-Internal-Secret', '')
    if expected and supplied and hmac.compare_digest(supplied, expected):
        return True

    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        return False
    audience = os.environ.get('TASKS_OIDC_AUDIENCE', '').strip()
    service_account = os.environ.get('TASKS_OIDC_SA', '').strip().casefold()
    if not audience or not service_account:
        return False
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token
        claims = id_token.verify_oauth2_token(
            authorization.removeprefix('Bearer ').strip(), Request(), audience=audience)
        return (str(claims.get('email') or '').casefold() == service_account
                and bool(claims.get('email_verified', True)))
    except Exception:
        return False
