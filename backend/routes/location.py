from flask import Blueprint, g, jsonify, request
from extensions import limiter
from middleware.auth import require_auth, require_verified_email
from services.location import resolve_area, LocationUnavailable

location_bp = Blueprint('location', __name__)


@location_bp.route('/resolve', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('30 per hour;6 per minute', key_func=lambda: g.user_id)
def resolve():
    try:
        result = resolve_area(request.get_json(silent=True), g.user_id)
    except ValueError:
        return jsonify(error='Invalid location request', code='invalid_location'), 400
    except LookupError:
        return jsonify(error='Area not found', code='area_not_found'), 404
    except LocationUnavailable:
        return jsonify(error='Area lookup is unavailable', code='location_unavailable'), 503
    response = jsonify(location=result)
    response.headers['Cache-Control'] = 'no-store'
    return response
