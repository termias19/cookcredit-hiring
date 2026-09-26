"""Resolve legacy recording references inside the configured bucket, never via HTTP.

An accepted URL is only an object locator. Its token does not confer ownership.
All access is bound to the authenticated owner and an immutable object generation.
"""
from datetime import timedelta
from urllib.parse import urlsplit, unquote
from services.firebase import STORAGE_BUCKET, get_storage_bucket
from services.storage_signing import signed_url

MAX_VIDEO_BYTES = 80 * 1024 * 1024
PLAYBACK_TTL_SECONDS = 300
VIDEO_TYPES = {'video/webm', 'video/mp4', 'video/quicktime'}


class InvalidRecording(ValueError):
    pass


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


def inspect_recording(url, owner_uid):
    path = owned_recording_path(url, owner_uid)
    blob = get_storage_bucket().blob(path)
    blob.reload(timeout=30)
    kind = (blob.content_type or '').split(';', 1)[0]
    if kind not in VIDEO_TYPES or not 0 < int(blob.size or 0) <= MAX_VIDEO_BYTES:
        raise InvalidRecording('Recording size or format is not supported.')
    if not blob.generation:
        raise InvalidRecording('Recording generation is missing.')
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


def playback_url(path, generation, owner_uid):
    # Recheck the stored grant, even though it was validated at consent time.
    from urllib.parse import quote
    owned_recording_path(f'https://firebasestorage.googleapis.com/v0/b/{STORAGE_BUCKET}/o/{quote(path, safe="")}', owner_uid)
    if not str(generation).isdigit():
        raise InvalidRecording('Recording generation is missing.')
    blob = get_storage_bucket().blob(path, generation=int(generation))
    return signed_url(blob,
        version='v4', method='GET', expiration=timedelta(seconds=PLAYBACK_TTL_SECONDS),
        query_parameters={'generation': str(generation)},
    )
