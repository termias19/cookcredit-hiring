"""Optional playback work on existing attempts and the existing dispatch tick.

Cloud Run Jobs provide isolation and zero idle workers. SQL owns retry/lease state;
there is no second queue, no inline decoder and no change to scoring or consent.
"""
import hashlib
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_, text
from models import SkillAttempt, AssessmentShare
from services.database import db_session
from services.assessment_media import MAX_VIDEO_BYTES, recording_view, _timestamp, owned_recording_path
from services.operations import emit_event
from services.playback_encoding import PROFILE

LEASE_SECONDS = 1200
MAX_TRIES = 3
LOCK = 635742019  # Transaction-scoped admission, not a new durable work system.


class JobStartError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__('Compression execution could not be started')


def now():
    return datetime.now(timezone.utc)


def derivative_path(path, generation):
    identity = hashlib.sha256(f'{path}#{generation}:{PROFILE}'.encode()).hexdigest()
    return f'hiring-playback/{PROFILE}/{identity}/playback.mp4'


def _shared(session, attempt):
    metadata = attempt.metadata_ or {}
    return session.query(AssessmentShare.id).filter(
        AssessmentShare.attempt_id == attempt.id, AssessmentShare.applicant_id == attempt.user_id,
        AssessmentShare.storage_path == metadata.get('recording_path'),
        AssessmentShare.storage_generation == str(metadata.get('recording_generation')),
        AssessmentShare.revoked_at.is_(None)).first() is not None


def _eligible(attempt):
    metadata = attempt.metadata_ or {}
    return (metadata.get('source') == 'cookcredit-skill-live'
            and metadata.get('recording_path') and str(metadata.get('recording_generation', '')).isdigit()
            and recording_view(metadata)['state'] == 'ready')


def ensure_compression_intent(attempt):
    """Commit alongside a new recording, without network work or a second outbox."""
    if attempt.compression_state is None and _eligible(attempt):
        attempt.compression_state = 'pending'
        attempt.compression_requested_at = attempt.compression_due_at = now()


def _discover():
    """Bounded, non-destructive backfill of older, still-consented recordings."""
    with db_session() as session:
        rows = (session.query(SkillAttempt).filter(SkillAttempt.compression_state.is_(None),
            SkillAttempt.metadata_['source'].astext == 'cookcredit-skill-live',
            session.query(AssessmentShare.id).filter(AssessmentShare.attempt_id == SkillAttempt.id,
                AssessmentShare.revoked_at.is_(None)).exists())
            .order_by(SkillAttempt.created_at, SkillAttempt.id).with_for_update(skip_locked=True).limit(50).all())
        for attempt in rows:
            ensure_compression_intent(attempt)
            if attempt.compression_state is None:
                attempt.compression_state, attempt.compression_error = 'skipped', 'original_unavailable'


def _event(event, aid, token, **fields):
    # Attempt/lease UUIDs correlate the DB intent and execution without identity,
    # object paths, decoder messages, credentials or applicant payloads.
    emit_event(event, attemptId=str(aid), processingReference=str(token), profile=PROFILE, **fields)


def _failure_code(error):
    from google.api_core.exceptions import Forbidden, DeadlineExceeded, ServiceUnavailable, TooManyRequests
    from requests.exceptions import Timeout, ConnectionError
    if isinstance(error, Forbidden): return 'storage_permission_denied'
    if isinstance(error, (DeadlineExceeded, Timeout)): return 'dependency_timeout'
    if isinstance(error, TooManyRequests): return 'dependency_rate_limit'
    if isinstance(error, (ServiceUnavailable, ConnectionError)): return 'dependency_unavailable'
    from services.operations import dependency_diagnostic
    category = dependency_diagnostic(error)
    return category['dependency'] + '_' + category['reason'] if category['dependency'] != 'unknown' else 'processing_dependency_failed'


def launch_job(attempt_id, token):
    job = os.getenv('HIRING_COMPRESSION_JOB', '')
    if not re.fullmatch(r'projects/cookcredit-scoring/locations/us-central1/jobs/cc-hiring-(?:stg-)?compression', job):
        raise RuntimeError('Invalid compression job configuration')
    from google.auth import default
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    with AuthorizedSession(credentials) as client:
        response = client.post(f'https://run.googleapis.com/v2/{job}:run', json={
            'overrides': {'containerOverrides': [{'args': [str(uuid.UUID(attempt_id)), str(uuid.UUID(token))]}],
                          'taskCount': 1, 'timeout': '900s'}}, timeout=15)
        if response.status_code != 200:
            raise JobStartError({401:'execution_authentication_failed', 403:'execution_permission_denied',
                404:'execution_job_missing', 429:'execution_rate_limit'}.get(response.status_code,
                    'execution_service_unavailable' if response.status_code >= 500 else 'execution_rejected'))
        result = response.json()
        if not result.get('name') or result.get('error'):
            raise JobStartError('execution_acknowledgement_missing')


def _claim():
    stamp = now()
    with db_session() as session:
        if not session.execute(text('SELECT pg_try_advisory_xact_lock(:lock)'), {'lock': LOCK}).scalar():
            return None
        active = session.query(func.count(SkillAttempt.id)).filter(
            SkillAttempt.compression_lease_until > stamp).scalar()
        # Hard safety ceiling; raising admission requires a capacity review.
        if active >= min(4, max(1, int(os.getenv('HIRING_COMPRESSION_MAX_ACTIVE', '2')))):
            return None
        attempt = (session.query(SkillAttempt).filter(
            SkillAttempt.compression_state.in_(('pending', 'running')),
            SkillAttempt.compression_due_at <= stamp,
            or_(SkillAttempt.compression_lease_until.is_(None), SkillAttempt.compression_lease_until <= stamp))
            .order_by(SkillAttempt.created_at, SkillAttempt.id).with_for_update(skip_locked=True).first())
        if attempt is None:
            return None
        if not _eligible(attempt) or not _shared(session, attempt):
            attempt.compression_state, attempt.compression_due_at = 'skipped', None
            attempt.compression_lease_id = attempt.compression_lease_until = None
            attempt.compression_error = 'consent_or_retention_changed'
            return None
        if (attempt.compression_count or 0) >= MAX_TRIES:
            attempt.compression_state, attempt.compression_due_at = 'failed', None
            attempt.compression_lease_id = attempt.compression_lease_until = None
            attempt.compression_error = 'retry_exhausted'
            _event('recording_compression_failed', attempt.id, uuid.uuid4(), severity='ERROR', code='retry_exhausted')
            return None
        token = uuid.uuid4()
        attempt.compression_state = 'pending'
        attempt.compression_lease_id = token
        attempt.compression_lease_until = stamp + timedelta(seconds=LEASE_SECONDS)
        attempt.compression_due_at = attempt.compression_lease_until
        attempt.compression_requested_at = attempt.compression_requested_at or stamp
        attempt.compression_count = (attempt.compression_count or 0) + 1
        return str(attempt.id), str(token)


def _finish(aid, token, state, *, code=None, derivative=None):
    with db_session() as session:
        attempt = session.query(SkillAttempt).filter_by(id=aid).with_for_update().one_or_none()
        if (not attempt or str(attempt.compression_lease_id) != str(token)
                or not attempt.compression_lease_until or attempt.compression_lease_until <= now()):
            return False
        if state == 'ready' and (not _shared(session, attempt) or not _eligible(attempt)):
            state, derivative, code = 'skipped', None, 'consent_or_retention_changed'
        if state == 'pending' and attempt.compression_count >= MAX_TRIES:
            state = 'failed'
        attempt.compression_state, attempt.compression_error = state, code
        attempt.compression_lease_id = attempt.compression_lease_until = None
        attempt.compression_due_at = now() + timedelta(seconds=60 * 2**attempt.compression_count) if state == 'pending' else None
        if derivative:
            attempt.metadata_ = {**(attempt.metadata_ or {}), 'playback_derivative': derivative}
        _event('recording_compression_' + state, aid, token,
               severity='ERROR' if state == 'failed' else 'WARNING' if state == 'pending' else 'INFO', code=code)
        return True


def drain_compression(*, send=None, limit=2):
    stats = dict(claimed=0, delivered=0, failed=0)
    if not os.getenv('HIRING_COMPRESSION_JOB'):
        return stats
    _discover()
    for _ in range(min(max(limit, 0), 4)):
        claimed = _claim()
        if not claimed:
            break
        aid, token = claimed
        stats['claimed'] += 1
        try:
            (send or launch_job)(aid, token)
            stats['delivered'] += 1
            _event('recording_compression_dispatched', aid, token)
        except Exception as exc:
            # A timeout may have started a job. Fence that delivery before a
            # retry; stale/duplicate workers cannot publish or extend retention.
            _finish(aid, token, 'pending', code=exc.code if isinstance(exc, JobStartError) else 'execution_start_failed')
            stats['failed'] += 1
    report_compression_health()
    return stats


def report_compression_health():
    with db_session() as session:
        failed, pending, oldest = session.query(
            func.count(SkillAttempt.id).filter(SkillAttempt.compression_state == 'failed'),
            func.count(SkillAttempt.id).filter(SkillAttempt.compression_state.in_(('pending', 'running'))),
            func.min(SkillAttempt.compression_requested_at).filter(
                SkillAttempt.compression_state.in_(('pending', 'running')))).one()
    age = max(0, int((now() - oldest).total_seconds())) if oldest else 0
    emit_event('queue_health', severity='ERROR' if failed or age >= 1800 else 'INFO',
               queue='recording_compression', failed=int(failed or 0), pending=int(pending or 0), oldestSeconds=age)


def process_recording(aid, token):
    """Job-only entry point. Each execution receives UUIDs, never paths or tokens."""
    aid, token = str(uuid.UUID(aid)), str(uuid.UUID(token))
    with db_session() as session:
        attempt = session.query(SkillAttempt).filter_by(id=aid).with_for_update().one_or_none()
        if (not attempt or str(attempt.compression_lease_id) != token
                or attempt.compression_state != 'pending' or attempt.compression_lease_until <= now()):
            return 'stale'
        if not _eligible(attempt) or not _shared(session, attempt):
            # Finish after releasing the transaction/row lock.
            eligible = False
        else:
            eligible = True
            attempt.compression_state = 'running'
        metadata, owner = dict(attempt.metadata_ or {}), attempt.user_id
    if not eligible:
        _finish(aid, token, 'skipped', code='consent_or_retention_changed')
        return 'skipped'
    _event('recording_compression_started', aid, token)
    from services.firebase import get_storage_bucket, STORAGE_BUCKET
    from services.assessment_media import recording_snapshot
    from services.playback_encoding import encode_playback, EncodingSkipped
    from scripts.inspect_hiring_video import VideoInspectionError
    from urllib.parse import quote
    from google.api_core.exceptions import NotFound, PreconditionFailed
    path, generation = metadata['recording_path'], metadata['recording_generation']
    # Revalidate persisted data before any storage call; no user-controlled URL
    # is ever fetched, and this identity cannot read the learning media library.
    owned_recording_path(f'https://firebasestorage.googleapis.com/v0/b/{STORAGE_BUCKET}/o/{quote(path, safe="")}', owner)
    try:
        bucket = get_storage_bucket()
        original = bucket.blob(path, generation=int(generation))
        original.reload(timeout=15, retry=None)
        snapshot = recording_snapshot(original)
        expires = _timestamp(snapshot['expiresAt'])
        if expires <= now() or not 0 < int(original.size or 0) <= MAX_VIDEO_BYTES:
            raise EncodingSkipped('original_unavailable')
        destination = bucket.blob(derivative_path(path, generation))
        # A process can stop after upload but before the SQL commit. Reuse only
        # a server-written, generation-bound result from this exact profile.
        try:
            destination.reload(timeout=15, retry=None)
        except NotFound:
            with tempfile.TemporaryDirectory(prefix='hiring-playback-') as directory:
                source = Path(directory) / ('source' + Path(path).suffix)
                target = Path(directory) / 'playback.mp4'
                with source.open('xb') as output:
                    original.download_to_file(output, if_generation_match=int(generation), timeout=60, retry=None)
                if source.stat().st_size != int(original.size):
                    raise VideoInspectionError('Source size changed')
                result = encode_playback(source, target)
                if expires <= now():
                    raise EncodingSkipped('original_expired')
                destination.metadata = {'profile': PROFILE, 'originalGeneration': str(generation),
                    'sourceIdentity': hashlib.sha256(path.encode()).hexdigest(),
                    'expiresAt': snapshot['expiresAt'], 'sourceSha256': result['sourceSha256'],
                    'playbackSha256': result['playbackSha256'], 'qualityGate': 'passed'}
                destination.cache_control = 'private, no-store'
                # Inherit the original clock. Lifecycle can target daysSinceCustomTime
                # on this derivative-only prefix without touching any originals.
                destination.custom_time = original.time_created
                try:
                    destination.upload_from_filename(str(target), content_type='video/mp4',
                        if_generation_match=0, checksum='crc32c', timeout=60, retry=None)
                except PreconditionFailed:
                    pass  # Another fenced execution already finalized this key.
                destination.reload(timeout=15, retry=None)
                _event('recording_compression_quality', aid, token, **result)
        stored = destination.metadata or {}
        if (stored.get('profile') != PROFILE or stored.get('qualityGate') != 'passed'
                or stored.get('originalGeneration') != str(generation)
                or stored.get('sourceIdentity') != hashlib.sha256(path.encode()).hexdigest()
                or stored.get('expiresAt') != snapshot['expiresAt']
                or destination.content_type != 'video/mp4'
                or not 0 < int(destination.size or 0) <= int(original.size) * .9):
            raise EncodingSkipped('derivative_metadata_gate')
        derivative = {'profile': PROFILE, 'generation': str(destination.generation),
                      'originalGeneration': str(generation), 'expiresAt': snapshot['expiresAt']}
        return 'ready' if _finish(aid, token, 'ready', derivative=derivative) else 'fenced'
    except EncodingSkipped as exc:
        code = str(exc) if str(exc) in ('original_unavailable', 'original_expired', 'unsupported_capture',
            'unsupported_color', 'timing_or_metadata_gate', 'insufficient_savings', 'quality_gate',
            'derivative_metadata_gate') else 'input_gate'
        _finish(aid, token, 'skipped', code=code)
        return 'skipped'
    except (VideoInspectionError, NotFound) as exc:
        _finish(aid, token, 'skipped', code='original_missing' if isinstance(exc, NotFound) else 'decoder_gate')
        return 'skipped'
    except Exception as exc:
        _finish(aid, token, 'pending', code=_failure_code(exc))
        return 'retry'


def compressed_playback_url(path, generation, owner, derivative, expires):
    """Called only AFTER the existing original/seat/company/consent checks."""
    if os.getenv('HIRING_COMPRESSED_PLAYBACK') != '1' or not isinstance(derivative, dict):
        return None
    if (derivative.get('profile') != PROFILE or str(derivative.get('originalGeneration')) != str(generation)
            or not str(derivative.get('generation', '')).isdigit()
            or _timestamp(derivative.get('expiresAt')) != expires or expires <= now()):
        return None
    from services.firebase import get_storage_bucket, STORAGE_BUCKET
    from services.storage_signing import signed_url
    from urllib.parse import quote
    owned_recording_path(f'https://firebasestorage.googleapis.com/v0/b/{STORAGE_BUCKET}/o/{quote(path, safe="")}', owner)
    try:
        blob = get_storage_bucket().blob(derivative_path(path, generation), generation=int(derivative['generation']))
        blob.reload(timeout=5, retry=None)
        metadata = blob.metadata or {}
        if (metadata.get('profile') != PROFILE or metadata.get('originalGeneration') != str(generation)
                or metadata.get('sourceIdentity') != hashlib.sha256(path.encode()).hexdigest()
                or _timestamp(metadata.get('expiresAt')) != expires or metadata.get('qualityGate') != 'passed'
                or blob.content_type != 'video/mp4' or not 0 < int(blob.size or 0) <= MAX_VIDEO_BYTES):
            raise ValueError('Invalid derivative')
        return signed_url(blob, version='v4', method='GET', expiration=min(now() + timedelta(seconds=300), expires),
                          query_parameters={'generation': str(derivative['generation'])})
    except Exception as exc:
        from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable, TooManyRequests, NotFound
        transient = isinstance(exc, (DeadlineExceeded, ServiceUnavailable, TooManyRequests))
        code = 'derivative_missing' if isinstance(exc, NotFound) else 'derivative_dependency_retry' if transient else 'derivative_validation_or_signing'
        emit_event('recording_compression_fallback', severity='WARNING' if transient else 'ERROR', code=code, profile=PROFILE)
        return None
