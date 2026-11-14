"""Resolve legacy recording references inside the configured bucket, never via HTTP.

An accepted URL is only an object locator. Its token does not confer ownership.
All access is bound to the authenticated owner and an immutable object generation.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, unquote
from services.firebase import STORAGE_BUCKET, get_storage_bucket
from services.storage_signing import signed_url

MAX_VIDEO_BYTES = 80 * 1024 * 1024
PLAYBACK_TTL_SECONDS = 300
VIDEO_TYPES = {'video/webm', 'video/mp4', 'video/quicktime'}
RECORDING_RETENTION_DAYS = 30


class InvalidRecording(ValueError):
    pass


class RecordingUnavailable(ValueError):
    """A consented recording has expired or its pinned object is absent."""
    def __init__(self, code):
        assert code in ('recording_expired', 'recording_missing')
        self.code = code
        super().__init__('Recording expired' if code == 'recording_expired' else 'Recording unavailable')


class RecordingPlaybackError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__('Recording playback is temporarily unavailable')


def _timestamp(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def recording_view(metadata, generation=None, *, now=None):
    """Constant-time availability projection; never infer expiry from consent dates.

    Unknown historical media remains checkable, without claiming it is ready.
    Presence is verified at playback, after authorization, rather than issuing a
    storage request for every applicant on every roster load.
    """
    stored = (metadata or {}).get('recording_availability', {})
    expected = generation or (metadata or {}).get('recording_generation') or (stored.get('generation') if isinstance(stored, dict) else None)
    if not isinstance(stored, dict) or str(stored.get('generation')) != str(expected):
        stored = {}
    expires = _timestamp(stored.get('expiresAt'))
    state = stored.get('state', 'unchecked')
    if state not in ('ready', 'unavailable', 'expired', 'unchecked'):
        state = 'unchecked'
    if expires and expires <= (now or datetime.now(timezone.utc)):
        state = 'expired'
    return {'state': state, 'expiresAt': expires.isoformat() if expires else None}


def recording_snapshot(blob, *, now=None):
    """Server-observed metadata for one immutable generation, without its path."""
    now = now or datetime.now(timezone.utc)
    created = getattr(blob, 'time_created', None)
    if not isinstance(created, datetime) or created.tzinfo is None:
        raise InvalidRecording('Recording creation metadata is unavailable.')
    created = created.astimezone(timezone.utc)
    return {'generation': str(blob.generation), 'state': 'ready',
            'createdAt': created.isoformat(),
            'expiresAt': (created + timedelta(days=RECORDING_RETENTION_DAYS)).isoformat(),
            'observedAt': now.isoformat()}


def owned_recording_path(url, owner_uid):
    if not isinstance(owner_uid, str) or not owner_uid or any(c in owner_uid for c in '/\\\x00'):
        raise InvalidRecording('A recording owner is required.')
    if not isinstance(url, str):
        raise InvalidRecording('A recording reference is required.')
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'firebasestorage.googleapis.com'
                or parsed.fragment):
            raise InvalidRecording('Unsupported recording reference.')
        prefix = f'/v0/b/{STORAGE_BUCKET}/o/'
        if not parsed.path.startswith(prefix):
            raise InvalidRecording('Recording must be in the configured bucket.')
        path = unquote(parsed.path[len(prefix):], errors='strict')
    except (ValueError, UnicodeError) as exc:
        raise InvalidRecording('Invalid recording reference.') from exc
    parts = path.split('/')
    legacy = path.startswith(f'skill_videos/{owner_uid}/')
    engine = (len(parts) == 6 and parts[:3] == ['cookcredit-skill', 'users', owner_uid]
              and parts[3] == 'assessments' and parts[4]
              and parts[5].startswith('recording.'))
    if ('\\' in path or '\x00' in path or any(p in ('.', '..', '') for p in parts)
            or not (legacy or engine)
            or not path.endswith(('.webm', '.mp4', '.mov'))):
        raise InvalidRecording('Recording does not belong to this applicant.')
    return path


def inspect_recording(url, owner_uid, *, observation=None):
    path = owned_recording_path(url, owner_uid)
    blob = get_storage_bucket().blob(path)
    blob.reload(timeout=30)
    kind = (blob.content_type or '').split(';', 1)[0]
    if kind not in VIDEO_TYPES or not 0 < int(blob.size or 0) <= MAX_VIDEO_BYTES:
        raise InvalidRecording('Recording size or format is not supported.')
    if not blob.generation:
        raise InvalidRecording('Recording generation is missing.')
    if observation is not None:
        observation.update(recording_snapshot(blob))
    return path, str(blob.generation), kind


def read_recording(url, owner_uid, generation, max_bytes=MAX_VIDEO_BYTES):
    path = owned_recording_path(url, owner_uid)
    if not str(generation).isdigit():
        raise InvalidRecording('A verified recording generation is required.')
    blob = get_storage_bucket().blob(path, generation=int(generation))
    blob.reload(timeout=30)
    kind = (blob.content_type or '').split(';', 1)[0]
    if kind not in VIDEO_TYPES or not 0 < int(blob.size or 0) <= min(max_bytes, MAX_VIDEO_BYTES):
        raise InvalidRecording('Recording size or format is not supported.')
    data = blob.download_as_bytes(if_generation_match=int(generation), timeout=120)
    if len(data) > min(max_bytes, MAX_VIDEO_BYTES):
        raise InvalidRecording('Recording exceeds the size limit.')
    return data, kind


def playback_url(path, generation, owner_uid, *, observation=None):
    # Recheck the stored grant, even though it was validated at consent time.
    from urllib.parse import quote
    owned_recording_path(f'https://firebasestorage.googleapis.com/v0/b/{STORAGE_BUCKET}/o/{quote(path, safe="")}', owner_uid)
    if not str(generation).isdigit():
        raise InvalidRecording('Recording generation is missing.')
    now = datetime.now(timezone.utc)
    observed = observation if observation is not None else {}
    previous = dict(observed)
    # Retention is an access boundary even while lifecycle deletion is pending.
    if str(previous.get('generation')) == str(generation):
        expires = _timestamp(previous.get('expiresAt'))
        if expires and expires <= now:
            observed.update(state='expired', observedAt=now.isoformat())
            raise RecordingUnavailable('recording_expired')
    blob = get_storage_bucket().blob(path, generation=int(generation))
    from google.api_core.exceptions import NotFound
    try:
        blob.reload(timeout=10, retry=None)
    except NotFound:
        # Preserve only server-observed expiry for the SAME generation. An old
        # or unavailable historical timestamp must never invent an expiry date.
        observed.clear()
        if str(previous.get('generation')) == str(generation):
            observed.update({key: previous[key] for key in ('createdAt', 'expiresAt') if key in previous})
        observed.update(generation=str(generation), state='unavailable', observedAt=now.isoformat())
        raise RecordingUnavailable('recording_missing') from None
    except Exception as exc:
        from google.api_core.exceptions import Forbidden, DeadlineExceeded, ServiceUnavailable
        category = ('storage_permission_denied' if isinstance(exc, Forbidden) else 'storage_timeout'
                    if isinstance(exc, DeadlineExceeded) else 'storage_unavailable'
                    if isinstance(exc, ServiceUnavailable) else 'storage_lookup_failed')
        raise RecordingPlaybackError(category) from None
    if (str(blob.generation) != str(generation) or
            (blob.content_type or '').split(';', 1)[0] not in VIDEO_TYPES or
            not 0 < int(blob.size or 0) <= MAX_VIDEO_BYTES):
        raise InvalidRecording('Recording metadata does not match the pinned file.')
    observed.clear()
    observed.update(recording_snapshot(blob, now=now))
    expires = _timestamp(observed['expiresAt'])
    if expires <= now:
        observed['state'] = 'expired'
        raise RecordingUnavailable('recording_expired')
    try:
        return signed_url(blob,
            version='v4', method='GET', expiration=min(now + timedelta(seconds=PLAYBACK_TTL_SECONDS), expires),
            query_parameters={'generation': str(generation)},
        )
    except Exception:
        raise RecordingPlaybackError('signing_failed') from None
