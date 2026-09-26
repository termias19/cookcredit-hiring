"""Partner API credentials and durable, signed webhook delivery."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import ssl
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

import urllib3
from cryptography.fernet import Fernet, InvalidToken
from flask import g, jsonify, request
from flask_limiter.constants import ExemptionScope
from flask_limiter.util import get_remote_address
from extensions import limiter
from services.partner_rate_limits import enforce_partner_limit

from models import Org, PartnerApiKey, PartnerInvitation, PartnerWebhook, PartnerWebhookDelivery
from services.database import db_session
from services.integration_access import integration_access

VALID_SCOPES = {
    'roles:read', 'invitations:write', 'applications:read',
    'assessments:read', 'assessments:write',
}
WEBHOOK_EVENTS = {
    # Current contract.
    'assessment.requested', 'assessment.invited', 'assessment.started',
    'assessment.processing', 'assessment.evidence_ready',
    'assessment.review_completed', 'assessment.expired', 'assessment.withdrawn',
    # Version-one compatibility events.
    'application.submitted', 'assessment.completed', 'application.withdrawn',
}
MAX_DELIVERY_ATTEMPTS = 10


def _utcnow():
    return datetime.now(timezone.utc)


def _api_key_hash(raw: str) -> str:
    pepper = os.getenv('PARTNER_API_KEY_PEPPER', '')
    return hashlib.sha256((pepper + raw).encode()).hexdigest()


def issue_api_key(*, org_id, name: str, scopes: list[str], created_by: str,
                  environment: str = 'live'):
    clean_scopes = sorted(set(scopes) & VALID_SCOPES)
    if not clean_scopes:
        raise ValueError('At least one API scope is required')
    prefix = secrets.token_urlsafe(9)
    if environment not in ('test', 'live'):
        raise ValueError('API key environment must be test or live')
    raw = f'cc_{environment}_{prefix}_{secrets.token_urlsafe(32)}'
    return PartnerApiKey(
        org_id=org_id, name=name[:100], key_prefix=f'cc_{environment}_{prefix}',
        secret_hash=_api_key_hash(raw), scopes=clean_scopes, created_by=created_by,
        environment=environment,
    ), raw


def require_partner_scope(scope):
    def decorator(fn):
        @limiter.exempt(flags=ExemptionScope.DEFAULT)
        @wraps(fn)
        def wrapped(*args, **kwargs):
            ip = get_remote_address()
            blocked = enforce_partner_limit('lookup-ip', ip)
            if blocked is not None:
                return blocked
            def invalid(message, status=401):
                limited = enforce_partner_limit('invalid-ip', ip)
                return limited if limited is not None else (jsonify(error=message), status)
            header = request.headers.get('Authorization', '')
            raw = header[7:].strip() if header.startswith('Bearer ') else ''
            if not raw.startswith(('cc_live_', 'cc_test_')) or len(raw) > 200:
                return invalid('Invalid API credential')
            now = _utcnow()
            with db_session() as session:
                key = session.query(PartnerApiKey).filter_by(secret_hash=_api_key_hash(raw)).one_or_none()
                if (not key or key.revoked_at or (key.expires_at and key.expires_at <= now)
                        or scope not in (key.scopes or [])):
                    return invalid('Invalid API credential or scope')
                org = session.get(Org, key.org_id)
                if not integration_access(org)['api']:
                    return jsonify(error='Integration subscription required', upgradeRequired=True), 402
                g.partner_org_id = key.org_id
                g.partner_key_id = key.id
                g.partner_environment = key.environment or 'live'
                blocked = enforce_partner_limit('company', key.org_id)
                if blocked is not None:
                    return blocked
                if not key.last_used_at or key.last_used_at < now - timedelta(minutes=5):
                    key.last_used_at = now
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def _fernet():
    key = os.getenv('WEBHOOK_SECRET_ENCRYPTION_KEY', '').encode()
    if not key:
        raise RuntimeError('Webhook secret encryption is not configured')
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError('Webhook secret encryption key is invalid') from exc


def encrypt_webhook_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_webhook_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError('Stored webhook secret cannot be decrypted') from exc


def validate_webhook_url(raw: str) -> str:
    value = str(raw or '').strip()
    if len(value) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Webhook URL is invalid')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Webhook URL is invalid') from exc
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Webhook URL must be an HTTPS URL without credentials or a fragment')
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('Webhook port is invalid')
    try:
        literal = ipaddress.ip_address(parsed.hostname)
        if not literal.is_global:
            raise ValueError('Webhook URL must use a public internet address')
    except ValueError as exc:
        if 'public internet' in str(exc):
            raise
    return value


def _assert_public_destination(url: str) -> list[str]:
    parsed = urlsplit(validate_webhook_url(url))
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise RuntimeError('Webhook host did not resolve')
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise RuntimeError('Webhook destination resolved to a non-public address')
    return list(dict.fromkeys(address[4][0] for address in addresses))


def _post_public_webhook(url, *, data, headers, timeout, allow_redirects, stream):
    """Pin the TCP connection to a checked IP, while validating TLS for the hostname.

    Resolve exactly once. A second DNS lookup for the hostname would allow a
    public address to change to a private destination between check and send.
    This direct pool also does not inherit environment proxy settings.
    """
    addresses = _assert_public_destination(url)
    parsed = urlsplit(url)
    host = parsed.hostname.encode('idna').decode('ascii')
    host_header = f'[{host}]' if ':' in host else host
    if parsed.port and parsed.port != 443:
        host_header += f':{parsed.port}'
    pool = urllib3.HTTPSConnectionPool(addresses[0], port=parsed.port or 443,
        server_hostname=host, assert_hostname=host, ssl_context=ssl.create_default_context(),
        maxsize=1, block=True, timeout=urllib3.Timeout(connect=timeout[0], read=timeout[1]))
    try:
        response = pool.urlopen('POST', (parsed.path or '/') + ('?'+parsed.query if parsed.query else ''),
            body=data, headers={**headers, 'Host': host_header},
            redirect=False, retries=False, preload_content=False, assert_same_host=False)
    except Exception:
        pool.close()
        raise
    class DeliveryResponse:
        status_code = response.status
        def close(self):
            try:
                response.close()
            finally:
                pool.close()
    return DeliveryResponse()


def emit_partner_event(session, *, org_id, event_type: str, data: dict) -> str | None:
    if event_type not in WEBHOOK_EVENTS:
        raise ValueError('Unsupported webhook event')
    environment = data.get('environment', 'live')
    if environment not in ('test', 'live'):
        raise ValueError('Unsupported webhook environment')
    hooks = (session.query(PartnerWebhook)
             .filter_by(org_id=org_id, active=True, environment=environment).all())
    matching = [hook for hook in hooks if event_type in (hook.event_types or [])]
    if not matching:
        return None
    event_id = uuid.uuid4()
    envelope = {
        'id': str(event_id), 'type': event_type, 'environment': environment,
        'createdAt': _utcnow().isoformat(), 'data': data,
    }
    for hook in matching:
        session.add(PartnerWebhookDelivery(
            webhook_id=hook.id, event_id=event_id, event_type=event_type,
            payload=envelope, status='pending', next_attempt_at=_utcnow()))
    return str(event_id)


def assessment_request_context(session, application_id) -> dict:
    """External identifiers attached to an application, when it came from a partner request."""
    item = (session.query(PartnerInvitation)
            .filter_by(application_id=application_id)
            .order_by(PartnerInvitation.created_at.desc()).first())
    if not item:
        return {}
    return {
        'assessmentRequestId': str(item.id),
        'environment': item.environment,
        'externalCandidateId': item.external_candidate_id,
        'externalJobId': item.external_job_id,
        'assessmentProfile': item.assessment_profile,
        'assessmentProfileVersion': item.assessment_profile_version,
        'returnUrl': item.return_url,
    }


def _sign(secret: str, timestamp: int, body: bytes) -> str:
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
    return f't={timestamp},v1={digest}'


def dispatch_partner_webhooks(*, send=None, limit=50) -> dict:
    send = send or _post_public_webhook
    limit = max(1, min(50, int(limit)))
    now = _utcnow()
    claimed = []
    with db_session() as session:
        rows = (session.query(PartnerWebhookDelivery)
                .filter(PartnerWebhookDelivery.status.in_(('pending', 'delivering')),
                        PartnerWebhookDelivery.next_attempt_at <= now,
                        ((PartnerWebhookDelivery.locked_until.is_(None)) |
                         (PartnerWebhookDelivery.locked_until <= now)))
                .order_by(PartnerWebhookDelivery.next_attempt_at, PartnerWebhookDelivery.id)
                .with_for_update(skip_locked=True).limit(limit).all())
        for row in rows:
            hook = session.get(PartnerWebhook, row.webhook_id)
            if not hook or not hook.active:
                row.status = 'failed'; row.last_error = 'webhook disabled'
                row.lock_token = None; row.locked_until = None
                continue
            # A crashed worker never reaches the response handler below. Enforce
            # the same budget when reclaiming its expired lease, before sending.
            if row.attempts >= MAX_DELIVERY_ATTEMPTS:
                row.status = 'failed'; row.last_error = 'delivery attempt budget exhausted'
                row.lock_token = None; row.locked_until = None
                continue
            token = uuid.uuid4()
            row.status = 'delivering'; row.lock_token = token
            # A batch can take longer than one HTTP timeout. Other workers must
            # not reclaim its later deliveries while this worker is still sending.
            row.locked_until = now + timedelta(minutes=10)
            row.attempts += 1
            claimed.append((row.id, token, hook.id, hook.url, hook.secret_ciphertext,
                            row.payload, row.attempts))

    stats = {'claimed': len(claimed), 'delivered': 0, 'failed': 0, 'retrying': 0}
    def deliver(item):
        _, _, _, url, ciphertext, payload, _ = item
        error = None
        response = None
        try:
            body = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
            timestamp = int(_utcnow().timestamp())
            response = send(url, data=body, headers={
                'Content-Type': 'application/json',
                'User-Agent': 'CookCredit-Webhooks/1.0',
                'CookCredit-Event-Id': payload['id'],
                'CookCredit-Signature': _sign(decrypt_webhook_secret(ciphertext), timestamp, body),
            }, timeout=(3, 10), allow_redirects=False, stream=True)
            if not 200 <= response.status_code < 300:
                error = f'HTTP {response.status_code}'
        except Exception:
            error = 'delivery_failed'
        finally:
            if response is not None and hasattr(response, 'close'):
                response.close()
        return item, error

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(deliver, claimed))
    for (delivery_id, token, hook_id, _, _, _, attempts), error in results:

        with db_session() as session:
            row = (session.query(PartnerWebhookDelivery)
                   .filter_by(id=delivery_id, lock_token=token).with_for_update().one_or_none())
            hook = session.get(PartnerWebhook, hook_id)
            if not row:
                continue
            row.lock_token = None; row.locked_until = None
            if error is None:
                row.status = 'delivered'; row.delivered_at = _utcnow(); row.last_error = None
                if hook: hook.failure_count = 0
                stats['delivered'] += 1
            elif attempts >= MAX_DELIVERY_ATTEMPTS:
                row.status = 'failed'; row.last_error = error
                if hook:
                    hook.failure_count += 1
                    if hook.failure_count >= 20:
                        hook.active = False; hook.disabled_at = _utcnow()
                stats['failed'] += 1
            else:
                row.status = 'pending'; row.last_error = error
                row.next_attempt_at = _utcnow() + timedelta(seconds=min(3600, 30 * (2 ** (attempts - 1))))
                if hook: hook.failure_count += 1
                stats['retrying'] += 1
    return stats
