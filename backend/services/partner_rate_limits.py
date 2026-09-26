"""Shared Redis budgets for partner companies and invalid credentials.

All company keys and API routes consume one company budget. Raw API keys are
never rate-limit identifiers. An IP ceiling separately bounds credential lookup.
"""
import math
import time
from flask import current_app, jsonify
from limits import parse_many
from extensions import limiter

BUDGETS = {
    'lookup-ip': '6000 per minute;120000 per hour',
    'invalid-ip': '60 per minute;200 per hour',
    'company': '60 per minute;2000 per hour',
}


def enforce_partner_limit(kind, identity):
    if not limiter.enabled or not current_app.config.get('RATELIMIT_ENABLED', True):
        return None
    try:
        for budget in parse_many(BUDGETS[kind]):
            identifiers = ('cookcredit-partner-'+kind, str(identity))
            if not limiter.limiter.hit(budget, *identifiers):
                window = limiter.limiter.get_window_stats(budget, *identifiers)
                response = jsonify(error='Too many requests. Please retry after the indicated delay.', code='rate_limited')
                response.status_code = 429
                response.headers['Retry-After'] = str(max(1, math.ceil(window.reset_time-time.time())))
                return response
    except Exception:
        # Do not fall back to per-instance counters when shared storage fails.
        response = jsonify(error='Request protection is temporarily unavailable. Please retry shortly.')
        response.status_code = 503
        response.headers['Retry-After'] = '5'
        return response
    return None
