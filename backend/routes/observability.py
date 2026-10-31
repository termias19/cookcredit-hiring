"""Bounded browser diagnostics. Accept categories, never raw errors or user data."""
import os
import re
from flask import Blueprint, jsonify, request, g
from extensions import limiter
from services.operations import emit_event

observability_bp = Blueprint('observability', __name__)
CODES = {'render_error', 'unhandled_error', 'unhandled_rejection', 'api_network_error',
         'api_timeout', 'api_response_invalid', 'google_signin_error'}
SCREENS = {'landing', 'auth', 'manager', 'applicant', 'assessment', 'other', 'home_customer', 'home_helper', 'home_operator'}


@observability_bp.post('/client-error')
@limiter.limit('10 per minute; 60 per hour')
def client_error():
    # No token is needed: login and initial render errors must also be visible.
    # The report is untrusted, uses shared IP rate limits and cannot carry free text.
    origin_setting = 'HOME_FRONTEND_ORIGINS' if os.getenv('COOKCREDIT_PRODUCT') == 'home-services' else 'FRONTEND_URL'
    origins = {v.strip().rstrip('/') for v in os.getenv(origin_setting, '').split(',') if v.strip()}
    if request.headers.get('Origin', '') not in origins:
        return jsonify(error='Forbidden'), 403
    if request.content_length is None or request.content_length > 2048:
        return jsonify(error='Invalid report'), 400
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {'code', 'screen', 'release', 'reference'}:
        return jsonify(error='Invalid report'), 400
    if (not isinstance(data.get('code'), str) or data['code'] not in CODES
            or not isinstance(data.get('screen'), str) or data['screen'] not in SCREENS):
        return jsonify(error='Invalid report'), 400
    reference = data.get('reference')
    release = data.get('release')
    if (not isinstance(reference, str) or not re.fullmatch(r'[a-f0-9]{32}', reference)
            or not isinstance(release, str) or not re.fullmatch(r'[a-f0-9]{40}|unrecorded', release)):
        return jsonify(error='Invalid report'), 400
    emit_event('client_error', severity='ERROR', code=data['code'], screen=data['screen'],
               clientRelease=release, clientReference=reference,
               requestId=getattr(g, 'request_id', None), source='untrusted_browser')
    return '', 204
