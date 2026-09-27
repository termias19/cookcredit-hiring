"""Owner-managed immutable price versions, using the existing Stripe subscription flow."""
import uuid
from sqlalchemy import text
from models.billing_catalog import HiringPrice
from services.database import db_session

DEFAULTS = [
    {'plan': plan, 'interval': interval, 'currency': 'usd', 'amount': amount,
     'limits': {'seats': seats, 'openRoles': roles, 'monthlyRequests': usage}}
    for plan, monthly, seats, roles, usage in [('team', 9900, 5, 5, 100), ('integration', 29900, 15, 25, 1000)]
    for interval, amount in [('month', monthly), ('year', monthly * 10)]
]

def validate_price(data):
    if not isinstance(data, dict) or set(data) - {'plan','interval','currency','amount','limits','previousId'}:
        raise ValueError('Enter supported price fields.')
    if data.get('plan') not in ('team','integration') or data.get('interval') not in ('month','year'):
        raise ValueError('Choose Team or Integration and monthly or annual billing.')
    if data.get('currency') != 'usd' or type(data.get('amount')) is not int or not 100 <= data['amount'] <= 10000000:
        raise ValueError('Enter a USD price between $1 and $100,000 in whole cents.')
    limits = data.get('limits')
    if not isinstance(limits, dict) or set(limits) != {'seats','openRoles','monthlyRequests'}:
        raise ValueError('Enter seat, open-role and monthly API request limits.')
    for key, maximum in [('seats', 1000), ('openRoles', 1000), ('monthlyRequests', 100000)]:
        if type(limits[key]) is not int or not 1 <= limits[key] <= maximum:
            raise ValueError('Plan limits must be positive whole numbers within the supported range.')
    previous = data.get('previousId')
    if previous:
        try: previous = uuid.UUID(previous)
        except (ValueError, TypeError, AttributeError): raise ValueError('Refresh the current price before saving.') from None
    return {key: data[key] for key in ('plan','interval','currency','amount','limits')} | {'previous_id': previous}

def current_price(session, plan, interval='month'):
    return session.query(HiringPrice).filter_by(plan=plan, interval=interval, active=True).one_or_none()

def catalog(session):
    return [row.to_dict() for row in session.query(HiringPrice).filter_by(active=True).order_by(HiringPrice.plan, HiringPrice.interval)]

def price_for_subscription(session, price_id):
    return session.query(HiringPrice).filter_by(stripe_price_id=price_id, state='published').one_or_none() if price_id else None

def publish_price(price_id, create=None):
    # Provider I/O is bounded and outside database locks. The persisted UUID makes retry idempotent.
    with db_session() as session:
        row = session.get(HiringPrice, price_id)
        if not row: raise LookupError('Price not found.')
        if row.active: return row.to_dict()
        if row.state != 'draft': raise ValueError('Save a new draft to replace a published price.')
        values = row.to_dict()
    if create is None:
        from services.stripe_service import create_hiring_price
        create = create_hiring_price
    provider_id = create(values)
    with db_session() as session:
        session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key': 'hiring-price:'+values['plan']+':'+values['interval']})
        row = session.query(HiringPrice).filter_by(id=price_id).with_for_update().one()
        if row.active: return row.to_dict()
        current = current_price(session, row.plan, row.interval)
        if (current.id if current else None) != row.previous_id:
            raise ValueError('The current price changed. Refresh and save a new draft.')
        if current: current.active = False
        session.flush()
        row.stripe_price_id = provider_id
        row.state = 'published'; row.active = True
        session.flush()
        return row.to_dict()
