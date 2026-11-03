"""Only the verified Home owner can prepare, read or trash outreach drafts."""
import os
import uuid
from flask import Blueprint, jsonify, request, g
from sqlalchemy import select
from extensions import limiter
from models.home_outreach import HomeCampaign
from services import home_outreach as outreach, home_customers as customers, home_visits as visits
from services import database
from routes.home_visits import home_auth, is_owner, principal, json_body

outreach_bp = Blueprint('home_outreach', __name__)


def owner():
    if not is_owner():
        visits.fail('forbidden', 'Only the Home owner can prepare outreach.', 403)


@outreach_bp.get('/outreach')
@home_auth
@limiter.limit('30 per minute', key_func=lambda:g.user_id)
def drafts():
    owner()
    with database.db_session() as session:
        query = select(HomeCampaign)
        if request.args.get('cursor'):
            try:
                query = query.where(HomeCampaign.id < uuid.UUID(request.args['cursor']))
            except ValueError:
                visits.fail('invalid_cursor', 'Refresh the draft list.')
        rows = session.execute(query.order_by(HomeCampaign.id.desc()).limit(31)).scalars().all()
        customers.audit(session, principal(), 'outreach_list_viewed', 'drafts')
        return jsonify(drafts=[row.to_dict() for row in rows[:30]], nextCursor=str(rows[29].id) if len(rows)>30 else None)


@outreach_bp.post('/outreach')
@outreach_bp.put('/outreach/<uuid:campaign_id>')
@home_auth
@limiter.limit('30 per hour', key_func=lambda:g.user_id)
def save(campaign_id=None):
    owner()
    actor, body = principal(), json_body()
    with database.db_session() as session:
        result = visits.command(session, actor, request.headers.get('Idempotency-Key'),
            'outreach:' + str(campaign_id), body, lambda:outreach.save(session, actor, body, campaign_id))
    return jsonify(result)


@outreach_bp.post('/outreach/email-preview')
@home_auth
@limiter.limit('30 per minute', key_func=lambda:g.user_id)
def email_preview():
    owner()
    body = json_body()
    visits.strict_object(body, ('subject','body','postalAddress','design'))
    result = outreach.render_email(body, os.environ['HOME_PUBLIC_URL'])
    return jsonify(result)
