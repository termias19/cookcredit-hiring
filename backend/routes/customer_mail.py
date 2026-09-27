"""Owner campaign controls and verified-account email preferences."""
import secrets
import uuid
from datetime import datetime, timezone
from flask import Blueprint, g, jsonify, request
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from extensions import limiter
from middleware.auth import require_auth, require_verified_email
from routes.hiring_access import owner_only
from models.account_email import AccountEmail
from models.customer_mail import Campaign, CampaignEvent, EmailPreference, now
from services.database import db_session

customer_mail_bp = Blueprint('customer_mail', __name__)


@customer_mail_bp.route('/preferences', methods=['GET', 'PUT'])
@require_auth
@require_verified_email
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def preferences():
    with db_session() as session:
        if request.method == 'PUT':
            data = request.get_json(silent=True) or {}
            if not isinstance(data, dict) or type(data.get('offers')) is not bool:
                return jsonify(error='Choose whether to receive offers.'), 400
            session.execute(insert(EmailPreference).values(user_id=g.user_id, email=g.email,
                opted_in=data['offers'], unsubscribe_token=secrets.token_urlsafe(32), updated_at=now())
                .on_conflict_do_update(index_elements=['user_id'], set_={
                    'email': g.email, 'opted_in': data['offers'], 'updated_at': now(),
                    'consent_version': 'hiring-offers-v1'}))
        row = session.get(EmailPreference, g.user_id)
        return jsonify(offers=bool(row and row.opted_in and row.email.casefold() == g.email.casefold()))


@customer_mail_bp.post('/unsubscribe')
@limiter.limit('30 per minute')
def unsubscribe():
    data = request.get_json(silent=True) or request.form
    token = (data.get('token') if hasattr(data, 'get') else None) or request.args.get('token')
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        return jsonify(error='This unsubscribe link is invalid.'), 400
    with db_session() as session:
        session.query(EmailPreference).filter_by(unsubscribe_token=token).update(
            {'opted_in': False, 'updated_at': now()}, synchronize_session=False)
    return jsonify(message='You will no longer receive Hiring offers. Account and payment messages remain enabled.')


@customer_mail_bp.get('/owner/campaigns')
@require_auth
@require_verified_email
@owner_only
def campaigns():
    with db_session() as session:
        query = session.query(Campaign)
        if request.args.get('cursor'):
            try:
                query = query.filter(Campaign.id < uuid.UUID(request.args['cursor']))
            except ValueError:
                return jsonify(error='Invalid cursor.'), 400
        rows = query.order_by(Campaign.id.desc()).limit(31).all()
        audience = session.query(func.count()).select_from(EmailPreference).filter_by(opted_in=True).scalar()
        counts = dict(session.query(AccountEmail.status, func.count()).filter(AccountEmail.kind.in_(
            ('billing_paid', 'billing_failed', 'campaign'))).group_by(AccountEmail.status).all())
        return jsonify(campaigns=[r.to_dict() for r in rows[:30]], audience=audience,
                       deliveryCounts=counts, nextCursor=str(rows[29].id) if len(rows) > 30 else None)


@customer_mail_bp.route('/owner/campaigns', methods=['POST'])
@customer_mail_bp.route('/owner/campaigns/<uuid:campaign_id>', methods=['PUT'])
@require_auth
@require_verified_email
@owner_only
@limiter.limit('60 per hour', key_func=lambda: g.user_id)
def save_campaign(campaign_id=None):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Enter campaign details.'), 400
    with db_session() as session:
        row = session.query(Campaign).filter_by(id=campaign_id).with_for_update().first() if campaign_id else Campaign()
        if not row:
            return jsonify(error='Campaign not found.'), 404
        if campaign_id and data.get('revision') != row.revision:
            return jsonify(error='This campaign changed. Refresh before saving.'), 409
        action = data.get('action', 'save')
        if action not in ('save', 'schedule', 'pause', 'trash', 'restore'):
            return jsonify(error='Choose a valid action.'), 400
        if not campaign_id and action != 'save':
            return jsonify(error='Save a draft first.'), 400
        if action in ('save', 'schedule'):
            if row.status == 'trashed':
                return jsonify(error='Restore this campaign first.'), 409
            for key, field, cap in [('subject', 'subject', 150), ('body', 'body', 10000), ('postalAddress', 'postal_address', 500)]:
                value = data.get(key, getattr(row, field) or '')
                if not isinstance(value, str) or len(value.strip()) > cap or (key == 'subject' and ('\n' in value or '\r' in value)):
                    return jsonify(error='Check the subject, message and address lengths.'), 400
                setattr(row, field, value.strip())
            if not row.subject or not row.body:
                return jsonify(error='Subject and message are required.'), 400
            interval = data.get('intervalDays', row.interval_days or 0)
            if type(interval) is not int or interval not in (0, 7, 30):
                return jsonify(error='Choose once, weekly or every 30 days.'), 400
            row.interval_days = interval
            row.status = 'draft'
        if action == 'schedule':
            if not row.postal_address:
                return jsonify(error='Add your business mailing address before scheduling offers.'), 400
            try:
                when = datetime.fromisoformat(data['nextRunAt'].replace('Z', '+00:00'))
                if when.tzinfo is None or when < now():
                    raise ValueError()
            except (KeyError, ValueError, TypeError, AttributeError):
                return jsonify(error='Choose a future date and time.'), 400
            row.status = 'scheduled'
            row.next_run_at = when
        elif action in ('pause', 'trash', 'restore'):
            row.status = {'pause': 'paused', 'trash': 'trashed', 'restore': 'draft'}[action]
        if action != 'schedule':
            row.next_run_at = None
        row.run_at = None
        row.cursor = None
        row.revision = (row.revision or 0) + 1
        row.updated_at = now()
        session.add(row)
        session.flush()
        session.add(CampaignEvent(campaign_id=row.id, actor_id=g.user_id, action=action))
        return jsonify(campaign=row.to_dict())
