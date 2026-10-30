"""Independent Home service application factory; never run with Hiring secrets.

Start with gunicorn 'home_app:create_app()'. The default serves only health and
503 responses. Enabling it requires explicit product, database and owner config.
"""
import os
import re
import time
import uuid
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from sqlalchemy import text
from sqlalchemy.engine import make_url
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from services import database
from services.home_visits import HomeError
from services.operations import emit_event


def database_url():
    if os.getenv('COOKCREDIT_PRODUCT') != 'home-services':
        raise RuntimeError('Home requires COOKCREDIT_PRODUCT=home-services')
    raw = os.getenv('HOME_DATABASE_URL', '')
    try:
        parsed = make_url(raw)
    except Exception:
        raise RuntimeError('Home requires its own HOME_DATABASE_URL') from None
    if parsed.drivername not in ('postgresql', 'postgresql+psycopg2'):
        raise RuntimeError('Home requires PostgreSQL')
    if not re.fullmatch(r'cookcredit_home_(dev|test|staging|prod)', parsed.database or ''):
        raise RuntimeError('Home must use a dedicated cookcredit_home database')
    if not re.fullmatch(r'cookcredit_home_(app|migrator)', parsed.username or ''):
        raise RuntimeError('Home must use its own database role')
    return raw


def create_app(config=None):
    app = Flask(__name__)
    # This entrypoint targets Cloud Run's single trusted reverse-proxy hop.
    # Do not trust forwarded Host, and do not expose this container directly.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024, HOME_ENABLED=os.getenv('HOME_SERVICES_ENABLED') == '1',
                      RATELIMIT_DEFAULT='60 per minute')
    if config:
        app.config.update(config)

    @app.before_request
    def trace():
        g.request_id, g.started = uuid.uuid4().hex, time.monotonic()
        if request.path != '/api/home/health' and not app.config['HOME_ENABLED']:
            return jsonify(error='Home services are not available yet.', code='home_disabled'), 503

    @app.after_request
    def finish(response):
        response.headers['X-Request-ID'] = g.request_id
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        if response.status_code == 503:
            response.headers['Retry-After'] = '5'
        if response.status_code >= 500:
            emit_event('home_request_failed', severity='ERROR', endpoint=request.endpoint or 'unmatched',
                status=response.status_code, durationMs=round((time.monotonic() - g.started) * 1000))
        return response

    @app.errorhandler(HomeError)
    def home_error(error):
        return jsonify(error=error.message, code=error.code), error.status

    @app.errorhandler(Exception)
    def unexpected(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.name, code='http_error'), error.code
        # Exception messages and traceback locals can contain household data or
        # SQL parameters. Only the class and server reference enter shared logs.
        emit_event('home_unhandled_error', severity='ERROR', exception=type(error).__name__)
        return jsonify(error='We could not finish that request. Please retry.',
                       code='temporary_error', reference=g.request_id), 503

    @app.get('/api/home/health')
    def health():
        if not app.config['HOME_ENABLED']:
            return jsonify(status='disabled', paymentsAvailable=False)
        with database.db_session() as session:
            session.execute(text("SELECT product FROM home_runtime_guard WHERE product = 'home-services'")).scalar_one()
        return jsonify(status='ok', paymentsAvailable=False)

    if app.config['HOME_ENABLED']:
        origins = [v.strip() for v in os.getenv('HOME_FRONTEND_ORIGINS', '').split(',') if v.strip()]
        if not app.testing:
            raw = database_url()
            ZoneInfo(os.getenv('HOME_SERVICE_TIMEZONE', 'America/New_York'))
            if make_url(raw).username != 'cookcredit_home_app':
                raise RuntimeError('Home runtime cannot use the migration role')
            if not os.getenv('HOME_OWNER_EMAILS', '').strip():
                raise RuntimeError('Home owner is not configured')
            if not origins or any(urlsplit(o).scheme != 'https' or urlsplit(o).path not in ('', '/')
                                  or urlsplit(o).query or urlsplit(o).fragment or not urlsplit(o).hostname
                                  or urlsplit(o).username or '*' in o for o in origins):
                raise RuntimeError('Home requires explicit HTTPS frontend origins')
            from services.firebase import init_firebase
            from extensions import limiter
            if not (os.getenv('RATELIMIT_STORAGE_URI') or os.getenv('REDIS_URL', '')).startswith(('redis://', 'rediss://')):
                raise RuntimeError('Home requires shared rate limit storage before public access')
            init_firebase()
            # Reuse bounded pooling/timeouts, with the Home-only URL. This process
            # runs no Hiring app and imports none of its blueprints.
            database.init_db(url=raw)
            with database.db_session() as session:
                session.execute(text("SELECT product FROM home_runtime_guard WHERE product = 'home-services'")).scalar_one()
            limiter.init_app(app)
        else:
            from extensions import limiter
            limiter.init_app(app)
        CORS(app, resources={r'/api/home/*': {'origins': origins}},
             allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'],
             methods=['GET', 'POST', 'PUT', 'OPTIONS'], expose_headers=['X-Request-ID'])
        from routes.home_visits import home_bp
        app.register_blueprint(home_bp, url_prefix='/api/home')
    return app
