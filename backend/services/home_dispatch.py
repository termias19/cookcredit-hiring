"""Home wakeup on the existing Cloud Tasks client; SQL remains authoritative."""
import os
import uuid
from urllib.parse import urlsplit


def enqueue(due):
    queue, target = os.getenv('HOME_TASKS_QUEUE', ''), os.getenv('HOME_TASKS_TARGET', '')
    if not queue and not target:
        return False
    audience, account = os.getenv('TASKS_OIDC_AUDIENCE', ''), os.getenv('TASKS_OIDC_SA', '')
    parsed = urlsplit(target)
    if not queue or not account or parsed.scheme != 'https' or target != audience + '/api/home/internal/dispatch':
        raise RuntimeError('Home task configuration invalid')
    from services.webhook_dispatch import _client
    from google.protobuf.timestamp_pb2 import Timestamp
    stamp = Timestamp()
    stamp.FromDatetime(due)
    _client().create_task(request={'parent': queue, 'task': {
        'name': queue + '/tasks/home-' + uuid.uuid4().hex, 'schedule_time': stamp,
        'dispatch_deadline': {'seconds': 180}, 'http_request': {'http_method': 'POST', 'url': target,
            'headers': {'Content-Type': 'application/json'}, 'body': b'{}',
            'oidc_token': {'service_account_email': account, 'audience': audience}}}}, retry=None, timeout=2)
    return True
