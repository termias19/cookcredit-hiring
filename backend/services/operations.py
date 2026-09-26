"""Privacy-safe operational events; never include tokens, addresses or payloads."""
import json
import os
from datetime import datetime, timezone
from sqlalchemy import func
from services.database import db_session


def emit_event(event, *, severity='INFO', **fields):
    print(json.dumps({'severity': severity, 'event': event,
        'service': os.getenv('K_SERVICE', 'local'),
        'revision': os.getenv('K_REVISION', 'local'),
        'commit': os.getenv('RELEASE_COMMIT', 'unrecorded'), **fields}), flush=True)


def report_queue_health(kind):
    if kind == 'email':
        from models.account_email import AccountEmail as model
        pending = ('pending', 'sending')
    elif kind == 'webhook':
        from models import PartnerWebhookDelivery as model
        pending = ('pending', 'delivering')
    else:
        raise ValueError('Unknown queue')
    with db_session() as session:
        failed = session.query(func.count(model.id)).filter(model.status == 'failed').scalar()
        count, oldest = session.query(func.count(model.id), func.min(model.created_at)).filter(model.status.in_(pending)).one()
    age = max(0, int((datetime.now(timezone.utc) - oldest).total_seconds())) if oldest else 0
    unhealthy = bool(failed or age >= 600)
    emit_event('queue_health', severity='ERROR' if unhealthy else 'INFO',
               queue=kind, failed=int(failed or 0), pending=int(count), oldestSeconds=age)
    return not unhealthy
