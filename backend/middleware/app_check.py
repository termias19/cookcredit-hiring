"""Verify Firebase App Check on browser-only account operations.

This attests the web app; Identity Platform reCAPTCHA enforcement separately
protects Firebase account creation and password sign-in from automated abuse.
"""
import os
from functools import wraps
from flask import jsonify, request
from services.runtime_config import deployment_environment
from services.firebase import get_auth


def require_app_check(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        enabled = os.environ.get('AUTH_APP_CHECK_REQUIRED') == '1'
        if not enabled and deployment_environment() == 'development':
            return fn(*args, **kwargs)
        allowed = {x.strip() for x in os.environ.get('FIREBASE_APP_CHECK_APP_IDS', '').split(',') if x.strip()}
        token = request.headers.get('X-Firebase-AppCheck', '')
        if not enabled or not allowed:
            return jsonify(error='Account protection is not configured. Please try later.'), 503
        if not token or len(token) > 8192:
            return jsonify(error='Please reload the page and complete the security check.'), 403
        try:
            get_auth()
            from firebase_admin import app_check
            claims = app_check.verify_token(token)
            if claims.get('app_id') not in allowed:
                raise ValueError('Unexpected app')
        except Exception:
            return jsonify(error='Please reload the page and complete the security check.'), 403
        return fn(*args, **kwargs)
    return wrapped
