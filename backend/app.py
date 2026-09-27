from flask import Flask, jsonify, request, g
import time
import uuid
from dotenv import load_dotenv
import datetime
import logging
import os

load_dotenv()

from services.scoring_dispatch import validate_dispatch_configuration
from services.runtime_config import validate_runtime_configuration, deployment_environment
validate_dispatch_configuration()
validate_runtime_configuration()

# Deployment market: US (Stripe/USD/EN) or ET / Ethiopia-Addis (Chapa+cash/ETB/AM).
# The beam + discovery code is identical across markets; only thin adapters differ.
MARKET = os.environ.get("MARKET", "US").upper()

from extensions import limiter
from services.database import init_db, check_connection
from routes.auth     import auth_bp
from routes.hiring_access import access_bp
from routes.customer_mail import customer_mail_bp
from routes.messages import messages_bp
from routes.profile  import profile_bp
from routes.reviews  import reviews_bp
from routes.skills   import skills_bp
from routes.assessments import assessments_bp
from routes.assessment_sharing import sharing_bp
from routes.hiring import hiring_bp
from routes.embed import embed_bp
from routes.partner import partner_bp
from routes.cook_application import cook_application_bp
from routes.business import business_bp
from routes.resume   import resume_bp
from routes.admin    import admin_bp
from routes.cooks    import cooks_bp
from routes.location import location_bp
from routes.beams    import beams_bp
from routes.beam_agent import beam_agent_bp
from routes.orders   import orders_bp
from routes.ethio    import ethio_bp

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 84 * 1024 * 1024

@app.before_request
def trace_request():
    # Generate our own ID: do not trust or log arbitrary caller header values.
    g.request_id = uuid.uuid4().hex
    g.request_started = time.monotonic()

@app.after_request
def trace_response(response):
    from services.operations import emit_event
    request_id = getattr(g, 'request_id', uuid.uuid4().hex)
    response.headers['X-Request-ID'] = request_id
    response.headers['Access-Control-Expose-Headers'] = 'X-Request-ID, X-Release-Commit, Retry-After'
    response.headers['X-Release-Commit'] = os.getenv('RELEASE_COMMIT', 'unrecorded')
    if response.status_code >= 500:
        emit_event('request_failed', severity='ERROR', requestId=request_id,
                   endpoint=request.endpoint or 'unmatched', status=response.status_code,
                   durationMs=round((time.monotonic()-getattr(g,'request_started',time.monotonic()))*1000))
    return response


# Behind Cloud Run's proxy, trust ONE hop of X-Forwarded-* so request.remote_addr is the real
# client IP (not the front-end proxy). Without this, every per-IP rate limit collapses to a single
# global bucket. Cloud Run is a single trusted proxy, so x_for=1 is correct.
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ── CORS ──────────────────────────────────────────────────────────────────────
_frontend = os.environ.get("FRONTEND_URL", "")
_extra    = [o.strip() for o in _frontend.split(",") if o.strip()] if _frontend else []
_dev      = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5203", "http://127.0.0.1:5203",
]
_prod     = [
    "https://cookcredit.com",
    "https://www.cookcredit.com",
    "https://project-foodnlit.web.app",
    "https://foodnlit-1123e.web.app",
    "https://foodnlit-1123e.firebaseapp.com",
    "https://cookcredit-knife-demo.web.app",
]
_origins  = list(dict.fromkeys(_extra if deployment_environment() in ('staging', 'production') else _dev + _prod + _extra))
print(f"CORS allowed origins: {_origins}", flush=True)

@app.route("/api/<path:path>", methods=["OPTIONS"])
@limiter.exempt
def handle_preflight(path):
    """Explicit OPTIONS handler — answers every CORS preflight before auth runs."""
    origin = request.headers.get("Origin", "")
    resp = app.make_response(("", 204))
    if origin in _origins:
        resp.headers["Access-Control-Allow-Origin"]      = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
        resp.headers["Access-Control-Allow-Headers"]     = "Content-Type, Authorization, X-CookCredit-Internal, X-Firebase-AppCheck"
        resp.headers["Access-Control-Allow-Methods"]     = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return resp

@app.after_request
def ensure_cors(response):
    """Add CORS headers to every response, including errors (401, 429, 500, etc.)."""
    origin = request.headers.get("Origin", "")
    if origin in _origins:
        response.headers["Access-Control-Allow-Origin"]      = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"]     = "Content-Type, Authorization, X-CookCredit-Internal, X-Firebase-AppCheck"
        response.headers["Access-Control-Allow-Methods"]     = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return response

# ── Rate limiting ─────────────────────────────────────────────────────────────
limiter.init_app(app)
# Per-route limits are applied in each blueprint file.
# No blueprint-level override — routes inherit the global default (200/hr, 60/min)
# and CRITICAL/SENSITIVE routes declare tighter UID-keyed limits directly.

# ── Database ───────────────────────────────────────────────────────────────────
init_db()

# ── Blueprints ────────────────────────────────────────────────────────────────
app.register_blueprint(auth_bp,     url_prefix="/api/auth")
app.register_blueprint(access_bp, url_prefix='/api/access')
app.register_blueprint(customer_mail_bp, url_prefix='/api/customer-mail')
app.register_blueprint(messages_bp, url_prefix="/api/messages")
app.register_blueprint(profile_bp,  url_prefix="/api/profile")
app.register_blueprint(reviews_bp,  url_prefix="/api/reviews")
# Stripe loads ONLY for the US market: Stripe does not operate in Ethiopia, and
# services.stripe_service binds stripe.api_key at import time, so an ET deploy must not
# import it at all. ET settlement (Chapa + cash-on-delivery) is handled separately.
if MARKET == "US":
    from routes.stripe import stripe_bp
    app.register_blueprint(stripe_bp, url_prefix="/api/stripe")
app.register_blueprint(skills_bp,   url_prefix="/api/skills")
app.register_blueprint(assessments_bp, url_prefix="/api/assessments")
app.register_blueprint(sharing_bp, url_prefix="/api/assessment-sharing")
app.register_blueprint(hiring_bp, url_prefix="/api/hiring")
app.register_blueprint(embed_bp, url_prefix="/api/embed")
app.register_blueprint(partner_bp, url_prefix="/api/partner")
app.register_blueprint(cook_application_bp, url_prefix="/api/cook-application")
app.register_blueprint(business_bp, url_prefix="/api/business")
app.register_blueprint(resume_bp,   url_prefix="/api/resume")
app.register_blueprint(admin_bp,    url_prefix="/api/admin")
app.register_blueprint(cooks_bp,    url_prefix="/api/cooks")
app.register_blueprint(location_bp, url_prefix="/api/location")
app.register_blueprint(beams_bp,    url_prefix="/api/beams")
app.register_blueprint(beam_agent_bp, url_prefix="/api/beams/agent")
app.register_blueprint(orders_bp,   url_prefix="/api/orders")
app.register_blueprint(ethio_bp,    url_prefix="/api/ethio")

# ── Request logging (Stripe endpoints) ────────────────────────────────────────
@app.before_request
def log_request():
    if request.path.startswith("/api/stripe"):
        authed = bool(request.headers.get("Authorization"))
        log.info("%s %s from %s auth=%s", request.method, request.path, request.remote_addr, authed)

# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/api/health")
@limiter.exempt
def health():
    db_ok = check_connection()
    return {"status": "ok" if db_ok else "degraded", "app": "CookCredit", "database": db_ok,
            "environment": deployment_environment(), "revision": os.environ.get('K_REVISION')}


@app.route('/api/ready')
@limiter.exempt
def ready():
    from services.readiness import readiness
    checks, ok = readiness(check_connection, limiter.storage)
    return jsonify(status='ready' if ok else 'unavailable', checks=checks,
                   environment=deployment_environment()), 200 if ok else 503

# ── Rate limit error handler ───────────────────────────────────────────────────
@app.errorhandler(429)
def ratelimit_handler(e):
    retry_after = 60
    current_limit = limiter.current_limit
    if current_limit is not None:
        import math
        retry_after = max(1, math.ceil(current_limit.reset_at - time.time()))
    if hasattr(e, "retry_after") and e.retry_after:
        reset = e.retry_after
        if isinstance(reset, datetime.datetime):
            now = datetime.datetime.now(datetime.timezone.utc)
            if reset.tzinfo is None:
                reset = reset.replace(tzinfo=datetime.timezone.utc)
            retry_after = max(1, int((reset - now).total_seconds()))
        else:
            retry_after = int(reset)
    resp = jsonify({"error": "Too many requests — slow down", "retry_after": retry_after})
    if retry_after is not None:
        resp.headers["Retry-After"] = str(retry_after)
    return resp, 429

# ── Generic error handlers ─────────────────────────────────────────────────────
# Clients get a stable, generic JSON shape; full detail (incl. tracebacks) goes to
# the SERVER logs only — never leak internals to a caller. Keeps responses JSON
# (not Flask's HTML error pages) and lets the after_request CORS headers apply.
from werkzeug.exceptions import HTTPException  # noqa: E402


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_e):
    return jsonify({"error": "Method not allowed"}), 405


@app.errorhandler(Exception)
def handle_exception(e):
    # Known HTTP errors keep their status + safe name; everything else is a
    # generic 500 with the real cause logged server-side only.
    if isinstance(e, HTTPException):
        return jsonify({"error": e.name}), e.code
    from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeout
    from redis.exceptions import RedisError
    from limits.errors import StorageError
    from services.email_capacity import EmailQueueBusy
    if isinstance(e, (OperationalError, PoolTimeout, RedisError, StorageError, EmailQueueBusy)):
        from services.operations import emit_event
        emit_event('dependency_unavailable', severity='ERROR', requestId=g.request_id,
                   exception=type(e).__name__, endpoint=request.endpoint or 'unmatched')
        response = jsonify(error='Temporarily busy. Please try again shortly.', requestId=g.request_id)
        response.status_code = 503
        response.headers['Retry-After'] = '60' if isinstance(e, EmailQueueBusy) else '5'
        return response
    import traceback
    from pathlib import Path
    from services.operations import emit_event
    emit_event('unhandled_exception', severity='ERROR', requestId=g.request_id,
               exception=type(e).__name__, endpoint=request.endpoint or 'unmatched',
               frames=[{'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
                       for frame in traceback.extract_tb(e.__traceback__)])
    return jsonify({"error": "Internal server error", "requestId": g.request_id}), 500


if __name__ == "__main__":
    app.run(debug=False, port=int(os.environ.get("PORT", 5000)))
