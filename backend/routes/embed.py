"""Public, origin-bound configuration for the subscription widget."""
import uuid

from flask import Blueprint, jsonify, request

from extensions import limiter
from models import Org, RolePosting
from routes.hiring import _public_role
from services.database import db_session
from services.integration_access import integration_access

embed_bp = Blueprint('embed', __name__)
COOKCREDIT_ORIGINS = {
    'https://cookcredit.com', 'https://www.cookcredit.com',
    'https://foodnlit-1123e.web.app', 'https://project-foodnlit.web.app',
    'http://localhost:5173',
}


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


@embed_bp.route('/v1/<public_key>/roles/<role_id>', methods=['GET'])
@limiter.limit('120 per minute')
def widget_role(public_key, role_id):
    origin = request.headers.get('Origin', '')
    rid = _uuid(role_id)
    with db_session() as session:
        org = session.query(Org).filter_by(public_embed_key=public_key[:200]).one_or_none()
        if not integration_access(org)['widget']:
            return jsonify(error='Widget unavailable'), 404
        allowed = set(org.embed_allowed_origins or []) | COOKCREDIT_ORIGINS
        if origin not in allowed:
            return jsonify(error='This website is not allowed to load the widget'), 403
        role = session.get(RolePosting, rid) if rid else None
        if (not role or role.org_id != org.id or role.status != 'open'
                or role.integration_managed or role.integration_environment != 'live'):
            return jsonify(error='Role unavailable'), 404
        payload = _public_role(role, org)
    response = jsonify(role=payload)
    response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Vary'] = 'Origin'
    response.headers['Cache-Control'] = 'public, max-age=60'
    return response, 200
