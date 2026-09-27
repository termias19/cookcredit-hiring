import hashlib
import os
import threading
import time
from functools import wraps

from flask import request, jsonify, g

from services.firebase import get_auth


# ── admin allowlist ──────────────────────────────────────────────────────────
# Who can approve cook applications. An env allowlist (ADMIN_EMAILS, comma-separated)
# keyed off the verified Firebase email — no DB column / admin-role migration needed,
# and an admin can't be self-granted from the client. Swap for a role table later.
def _admin_emails() -> set:
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_admin_email(email: str) -> bool:
    return bool(email) and email.strip().lower() in _admin_emails()


def admin_only(f):
    """Gate a route to platform admins. Apply BELOW @require_auth (which sets g.email).
    403s a non-admin. The check is on the verified token email, never client input."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_admin_email(getattr(g, "email", "")):
            return jsonify({"error": "forbidden"}), 403
        return f(*args, **kwargs)
    return decorated


def require_verified_email(f):
    """Gate a privileged route to users who have VERIFIED their email. Apply BELOW @require_auth
    (which sets g.email_verified from the verified token), ABOVE any @limiter.limit so an unverified
    caller is rejected before consuming a rate token. 403s an unverified caller.

    This is the server-side enforcement that makes bot / disposable-email signups INERT: an account
    that can't receive the verification email can never reach a real action. The frontend already
    blocks unverified login, so legitimate in-app users are always verified and pass cleanly — this
    just closes the gap where a token from an unverified account hits the API directly.

    The client must refresh its token after verification; privileged routes
    enforce this decorator in addition to company/owner authorization.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not getattr(g, "email_verified", False):
            return jsonify({"error": "Please verify your email to continue.",
                            "code": "email_unverified"}), 403
        return f(*args, **kwargs)
    return decorated

# ── verified-token cache ─────────────────────────────────────────────────────
# Firebase verify_id_token() is a NETWORK call to Google on every request. The
# same short-lived ID token hits us many times in a session, so we cache the
# decoded claims for a short window and skip the round-trip on repeats. This
# removes ~100-300 ms (and a blocking call) from the hot path of every protected
# endpoint. Trade-off: a revoked token keeps working for up to _TTL seconds.
# In-process per gunicorn worker (no infra); swap for Redis when multi-instance.
# We key by SHA-256 of the token, never storing the raw token.
_TTL = 30        # max seconds to trust a cached verification
_SKEW = 30        # never cache past (token-exp - skew)
_MAX = 5000       # bound memory
_cache = {}       # sha256(token) -> (claims, expiry_epoch)
_lock = threading.Lock()


def _verify_token(token: str) -> dict:
    """Verify a Firebase ID token, using a short-TTL cache to avoid re-hitting
    Google on every request. Raises (like verify_id_token) on an invalid token."""
    key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and hit[1] > now:
            return hit[0]

    claims = get_auth().verify_id_token(token, check_revoked=True)

    exp = float(claims.get("exp", now + _TTL))
    ttl = min(_TTL, max(0.0, exp - now - _SKEW))
    if ttl > 0:
        with _lock:
            if len(_cache) >= _MAX:
                _cache.clear()           # crude bound; cheap and rare
            _cache[key] = (claims, now + ttl)
    return claims


def require_auth(f):
    """Protect a route: verify `Authorization: Bearer <firebase_id_token>` and
    attach the user to Flask's `g` (g.user_id / g.email / g.name)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == "OPTIONS":
            return "", 204

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split("Bearer ")[1].strip()
        try:
            decoded = _verify_token(token)
            g.user_id = decoded["uid"]
            g.email   = decoded.get("email", "")
            g.name    = decoded.get("name", "")
            g.email_verified = bool(decoded.get("email_verified", False))
        except Exception:
            # Don't echo the verifier's internal reason back to the caller.
            return jsonify({"error": "Invalid or expired token"}), 401

        # Hiring has shared Firebase identities but separately approved API access.
        from services.hiring_access import enabled, access_allowed
        if os.environ.get('COOKCREDIT_ENVIRONMENT') == 'staging' or enabled():
            allowed = {x.strip().casefold() for x in os.environ.get('STAGING_ALLOWED_EMAILS', '').split(',') if x.strip()}
            if not allowed and not enabled():
                return jsonify(error='Staging access is not configured'), 503
            # Employer approval does not apply to applicants following public role links.
            # These routes still enforce identity, verified email, ownership and consent.
            applicant_route = enabled() and (request.endpoint, request.method) in {
                ('auth.sync_user', 'POST'), ('auth.get_me', 'GET'),
                ('auth.update_me', 'PATCH'), ('auth.request_verification_email', 'POST'),
                ('auth.complete_verification', 'POST'),
                ('customer_mail.preferences', 'GET'), ('customer_mail.preferences', 'PUT'),
                ('hiring.apply', 'POST'), ('hiring.my_application', 'GET'),
                ('hiring.get_application', 'GET'), ('hiring.my_applications', 'GET'),
                ('hiring.start_attempt', 'POST'), ('hiring.complete_attempt', 'POST'),
                ('hiring.get_assessment_session', 'GET'),
                ('hiring.withdraw_application', 'POST'), ('hiring.application_cv', 'GET'),
            }
            if not applicant_route and not access_allowed(g.email):
                return jsonify(error='Employer access requires approval from CookCredit', code='staging_access_denied'), 403
            # An invited new account must be able to create its own inert
            # profile before email verification. Otherwise signup stops at
            # /sync and never reaches the verification-email step. Exact
            # endpoints and methods prevent this exception opening other APIs.
            bootstrap = (request.endpoint, request.method) in {
                ('auth.sync_user', 'POST'), ('auth.get_me', 'GET'),
                ('auth.request_verification_email', 'POST'),
            }
            if not g.email_verified and not bootstrap:
                return jsonify(error='Please verify your email to continue.', code='email_unverified'), 403

        return f(*args, **kwargs)
    return decorated
