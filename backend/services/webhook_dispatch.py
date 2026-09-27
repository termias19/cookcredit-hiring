"""Best-effort fast wakeup; PostgreSQL remains the authoritative delivery queue."""
import os
import uuid
from functools import lru_cache
from urllib.parse import urlsplit


def request_dispatch(session, due_at, *, kind='webhook'):
    if kind not in ('webhook', 'billing'):
        raise ValueError('Unsupported dispatch kind')
    previous = session.info.get(f'{kind}_dispatch_due')
    if previous is None or due_at < previous:
        session.info[f'{kind}_dispatch_due'] = due_at


@lru_cache(maxsize=1)
def _client():
    from google.cloud import tasks_v2
    return tasks_v2.CloudTasksClient()


def enqueue_dispatch(due_at, *, kind='webhook'):
    if kind not in ('webhook', 'billing'):
        raise ValueError('Unsupported dispatch kind')
    queue = os.environ.get(f'{kind.upper()}_TASKS_QUEUE', '').strip()
    target = os.environ.get(f'{kind.upper()}_TASKS_TARGET', '').strip()
    if not queue and not target:
        return False  # Existing scheduler-only deployments remain supported.
    account = os.environ.get('TASKS_OIDC_SA', '').strip()
    audience = os.environ.get('TASKS_OIDC_AUDIENCE', '').strip()
    parsed = urlsplit(target)
    if (not queue or not account or not audience or parsed.scheme != 'https'
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or f'{parsed.scheme}://{parsed.netloc}' != audience
            or parsed.path != ('/api/partner/internal/dispatch-webhooks' if kind == 'webhook'
                               else '/api/stripe/internal/dispatch-events')):
        raise RuntimeError('Webhook task configuration is incomplete or invalid')
    from google.protobuf.timestamp_pb2 import Timestamp
    scheduled = Timestamp()
    scheduled.FromDatetime(due_at)
    _client().create_task(request={'parent': queue, 'task': {
        'name': f'{queue}/tasks/{kind}-{uuid.uuid4().hex}',
        'schedule_time': scheduled,
        'dispatch_deadline': {'seconds': 180},
        'http_request': {
            'http_method': 'POST', 'url': target,
            'headers': {'Content-Type': 'application/json'}, 'body': b'{"limit":10}',
            'oidc_token': {'service_account_email': account, 'audience': audience},
        },
    }}, retry=None, timeout=2)
    return True
