"""Privacy-safe operational events; never include tokens, addresses or payloads."""
import json
import os
import re
from datetime import datetime, timezone
from flask import g, has_request_context
from sqlalchemy import func, select, or_, and_, literal
from services.database import db_session


def emit_event(event, *, severity='INFO', **fields):
    # Correlate maintenance/probe events with the API response using only the
    # server-generated ID. Background jobs and local checks need no HTTP context.
    if has_request_context():
        reference = getattr(g, 'request_id', None)
        if isinstance(reference, str) and re.fullmatch(r'[a-f0-9]{32}', reference):
            fields.setdefault('requestId', reference)
    print(json.dumps({'severity': severity, 'event': event,
        'service': os.getenv('K_SERVICE', 'local'),
        'revision': os.getenv('K_REVISION', 'local'),
        'commit': os.getenv('RELEASE_COMMIT', 'unrecorded'), **fields}), flush=True)


def report_queue_health(kind):
    if kind in ('home_financial','home_events'):
        return _report_home_queue(kind)
    if kind == 'billing':
        from models import StripeEvent as model
        pending_filter = (model.processed_at.is_(None) & model.payload.isnot(None) & (model.attempts < 24))
        with db_session() as session:
            failed, count, oldest = session.query(
                func.count(model.id).filter(model.processed_at.is_(None), model.attempts >= 24),
                func.count(model.id).filter(pending_filter),
                func.min(model.received_at).filter(pending_filter)).one()
        return _report(kind, failed, count, oldest)
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
    return _report(kind, failed, count, oldest)


def _report_home_queue(kind):
    """Constant-size aggregates over existing durable records, never payloads.

    A transfer can legitimately wait for its source charge's funds. Give that
    specific pre-mutation state a separate seven-day operational escalation
    window; this is an alarm policy, not a promise of Stripe settlement timing.
    Other stalled work alerts after ten minutes. Review/held money and expired
    leases need attention immediately; a canonically recovered superseded
    reversal is intentionally held and does not need another financial action.
    """
    from models.home_service import HomeFinancialOperation,HomeStripeEvent,HomePayment
    model=HomeFinancialOperation if kind=='home_financial'else HomeStripeEvent
    stamp=datetime.now(timezone.utc)
    active=model.status.in_(('pending','retry','running'))
    review=model.status=='review_required'
    expired=and_(model.status=='running',or_(model.lease_until.is_(None),model.lease_until<stamp))
    if kind=='home_financial':
        waiting=and_(active,model.kind=='transfer',model.last_error=='funds_pending',model.mutation_started_at.is_(None)).is_(True)
        held=and_(model.status=='held',or_(model.last_error.is_(None),model.last_error!='external_transfer_recovered'))
        payment_reviews=select(func.count(HomePayment.id)).where(or_(
            HomePayment.status=='review_required',HomePayment.disputed.is_(True))).scalar_subquery()
    else:
        waiting=literal(False)
        held=literal(False)
        payment_reviews=literal(0)
    actionable=and_(active,~waiting)
    with db_session()as session:
        failed,count,oldest,held_count,expired_count,waiting_count,waiting_oldest,payment_review_count=session.query(
            func.count(model.id).filter(review),
            func.count(model.id).filter(actionable),func.min(model.created_at).filter(actionable),
            func.count(model.id).filter(held),func.count(model.id).filter(expired),
            func.count(model.id).filter(waiting),func.min(model.created_at).filter(waiting),payment_reviews,
        ).filter(model.status.in_(('pending','retry','running','held','review_required'))).one()
    age=max(0,int((stamp-oldest).total_seconds()))if oldest else 0
    waiting_age=max(0,int((stamp-waiting_oldest).total_seconds()))if waiting_oldest else 0
    overdue_waiting=bool(waiting_count and waiting_age>=7*86400)
    unhealthy=bool(failed or held_count or expired_count or payment_review_count or age>=600 or overdue_waiting)
    emit_event('queue_health',severity='ERROR'if unhealthy else'INFO',queue=kind,
        failed=int(failed or 0),pending=int(count or 0),oldestSeconds=age,
        held=int(held_count or 0),expiredLeases=int(expired_count or 0),
        paymentReviews=int(payment_review_count or 0),expectedWaiting=int(waiting_count or 0),
        expectedWaitingOldestSeconds=waiting_age,expectedWaitingOverdue=overdue_waiting)
    return not unhealthy


def _report(kind, failed, count, oldest):
    age = max(0, int((datetime.now(timezone.utc) - oldest).total_seconds())) if oldest else 0
    unhealthy = bool(failed or age >= 600)
    emit_event('queue_health', severity='ERROR' if unhealthy else 'INFO',
               queue=kind, failed=int(failed or 0), pending=int(count), oldestSeconds=age)
    return not unhealthy
