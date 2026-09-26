"""Durable scoring intent on SkillAttempt; no network I/O inside row locks.

An authenticated scheduler drains bounded batches. Unfinished work stays due even
after successful delivery, so queue deletion and exhausted queue retries recover.
Worker leases and terminal states make duplicate delivery safe for persisted results.
"""
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import or_
from models import SkillAttempt, ATTEMPT_TERMINAL
from services.database import db_session

log = logging.getLogger(__name__)
DISPATCH_LEASE_SECONDS = 90
DELIVERY_RECOVERY_SECONDS = 900


def validate_dispatch_configuration():
    """Fail a Cloud Run startup before it can accept work without queue configuration.

    This validates configuration shape only; staging must verify IAM and the actual
    scheduler/queue. Local tests and development do not require cloud credentials.
    """
    if not os.environ.get('K_SERVICE'):
        return
    missing = [key for key in ('TASKS_QUEUE', 'TASKS_TARGET_URL', 'TASKS_OIDC_SA', 'INTERNAL_SECRET')
               if not os.environ.get(key, '').strip()]
    if missing:
        raise RuntimeError('Missing scoring dispatch settings: ' + ', '.join(missing))
    if os.environ.get('SCORING_ALLOW_INLINE') == '1':
        raise RuntimeError('Inline scoring is forbidden on Cloud Run')
    if not re.fullmatch(r'projects/[^/\s]+/locations/[^/\s]+/queues/[^/\s]+', os.environ['TASKS_QUEUE']):
        raise RuntimeError('TASKS_QUEUE must be a fully qualified queue name')
    target = urlsplit(os.environ['TASKS_TARGET_URL'])
    if (target.scheme != 'https' or not target.hostname or target.username or target.password
            or target.query or target.fragment or target.path != '/api/skills/recompute'):
        raise RuntimeError('TASKS_TARGET_URL must be the HTTPS assessment recompute endpoint')
    if not os.environ['TASKS_OIDC_SA'].endswith('.iam.gserviceaccount.com'):
        raise RuntimeError('TASKS_OIDC_SA must be a Google service account email')


def retry_delay(failures):
    return min(900, 30 * 2 ** min(max(failures - 1, 0), 5))


def drain_scoring_dispatch(*, send=None, limit=50, time_budget=40):
    """Claim one item at a time, at most 50 per call and a soft 40-second budget.

    A process crash leaves a 90-second dispatch lease. Every recovered dispatch
    gets a new task name so Cloud Tasks' completed-name dedup window cannot strand
    it. Concurrent drainers skip locked rows; worker start fences dispatch updates.
    """
    if send is None:
        from services.skill_attempts import enqueue_recompute
        send = enqueue_recompute
    stats = dict(claimed=0, delivered=0, failed=0)
    started = time.monotonic()
    for _ in range(max(0, min(limit, 50))):
        if time.monotonic() - started >= time_budget:
            break
        now = datetime.now(timezone.utc)
        token = uuid.uuid4()
        with db_session() as session:
            attempt = (session.query(SkillAttempt)
                       .filter(SkillAttempt.verification_state.in_(['PROVISIONAL', 'VERIFYING']),
                               SkillAttempt.dispatch_due_at <= now,
                               or_(SkillAttempt.recompute_lease_until.is_(None),
                                   SkillAttempt.recompute_lease_until <= now))
                       .order_by(SkillAttempt.dispatch_due_at, SkillAttempt.id)
                       .with_for_update(skip_locked=True).first())
            if attempt is None:
                break
            attempt.dispatch_token = token
            attempt.dispatch_due_at = now + timedelta(seconds=DISPATCH_LEASE_SECONDS)
            attempt_id = str(attempt.id)
        stats['claimed'] += 1
        succeeded = False
        try:
            send(attempt_id, dispatch_id=str(token))
            succeeded = True
            stats['delivered'] += 1
        except Exception:
            stats['failed'] += 1
            log.exception('scoring dispatch failed for %s', attempt_id)
        with db_session() as session:
            attempt = session.query(SkillAttempt).filter_by(id=attempt_id).with_for_update().one_or_none()
            if attempt is None or attempt.dispatch_token != token:
                continue  # Worker or a newer dispatcher now owns scheduling.
            attempt.dispatch_token = None
            if attempt.verification_state in ATTEMPT_TERMINAL:
                attempt.dispatch_due_at = None
                continue
            attempt.dispatch_failures = 0 if succeeded else attempt.dispatch_failures + 1
            delay = DELIVERY_RECOVERY_SECONDS if succeeded else retry_delay(attempt.dispatch_failures)
            attempt.dispatch_due_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    log.info('scoring dispatch batch: %s', stats)
    return stats
