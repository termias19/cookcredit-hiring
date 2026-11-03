"""Home wakeup on the existing Cloud Tasks client; SQL remains authoritative."""
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit


def _utcnow():
    return datetime.now(timezone.utc)


def enqueue(due):
    queue, target = os.getenv('HOME_TASKS_QUEUE', ''), os.getenv('HOME_TASKS_TARGET', '')
    if not queue and not target:
        return False
    audience, account = os.getenv('TASKS_OIDC_AUDIENCE', ''), os.getenv('TASKS_OIDC_SA', '')
    parsed = urlsplit(target)
    if not queue or not account or parsed.scheme != 'https' or target != audience + '/api/home/internal/dispatch':
        raise RuntimeError('Home task configuration invalid')
    from services.webhook_dispatch import _client
    from google.api_core.exceptions import AlreadyExists
    from google.protobuf.timestamp_pb2 import Timestamp
    # Schedule ahead before coalescing. A completed task's retained ID must not
    # swallow an event committed after that task drained the durable queue.
    due = max(due, _utcnow() + timedelta(seconds=2))
    stamp = Timestamp()
    stamp.FromDatetime(due)
    task = {'parent': queue, 'task': {
        'name': queue + '/tasks/home-' + str(int(due.timestamp()) // 2), 'schedule_time': stamp,
        'dispatch_deadline': {'seconds': 180}, 'http_request': {'http_method': 'POST', 'url': target,
            'headers': {'Content-Type': 'application/json'}, 'body': b'{}',
            'oidc_token': {'service_account_email': account, 'audience': audience}}}}
    try:
        _client().create_task(request=task, retry=None, timeout=2)
    except AlreadyExists:
        return True
    return True


def request_next(session, *, notifications_not_before=None):
    """Wake the same worker for remaining batches, scheduled retries or leases."""
    from sqlalchemy import select, func, union_all, case
    from models.account_email import AccountEmail
    from models.home_service import HomeNotificationCursor, HomeFinancialOperation, HomeStripeEvent
    candidates = []
    if os.getenv('HOME_EMAILS_ENABLED') == '1':
        notification_due = HomeNotificationCursor.created_at
        if notifications_not_before is not None:
            notification_due = func.greatest(notification_due, notifications_not_before)
        candidates.extend([select(func.min(AccountEmail.available_at).label('due')).where(AccountEmail.status == 'pending'),
            select(func.min(AccountEmail.lease_until).label('due')).where(AccountEmail.status == 'sending'),
            select(func.min(notification_due).label('due')).where(HomeNotificationCursor.status == 'pending')])
    from services.home_stripe import mode
    for model in ((HomeFinancialOperation, HomeStripeEvent) if mode() != 'off' else ()):
        candidates.append(select(func.min(case((model.status == 'running', model.lease_until), else_=model.available_at)).label('due'))
            .where(model.status.in_(('pending', 'retry', 'running'))))
    if not candidates:
        return None
    combined = union_all(*candidates).subquery()
    due = session.execute(select(func.min(combined.c.due))).scalar_one()
    if due is not None:
        session.info['home_dispatch_due'] = due
    return due
