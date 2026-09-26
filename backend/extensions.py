import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Created here (without app) so route blueprints can import it without circular imports.
# app.py calls limiter.init_app(app) after creating the Flask instance.
#
# Key strategy:
#   - Default key is IP address (covers unauthenticated + webhook routes)
#   - Authenticated routes override with key_func=lambda: g.user_id (set by @require_auth)
#   - Decorator order for UID keying must be: @require_auth ABOVE @limiter.limit
#
# Storage: set RATELIMIT_STORAGE_URI (or REDIS_URL) to a Redis instance in
# production so limits are enforced ACROSS all gunicorn workers and app instances
# — in-memory counters are per-process and reset on restart, so behind a load
# balancer they barely limit anything. Falls back to memory:// for local dev.
_storage = (os.environ.get("RATELIMIT_STORAGE_URI")
            or os.environ.get("REDIS_URL")
            or "memory://")

limiter = Limiter(
    get_remote_address,
    default_limits=["200 per hour", "60 per minute"],
    storage_uri=_storage,
    strategy="fixed-window",
)
