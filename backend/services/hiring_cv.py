"""Private CV storage. Files are opaque attachments, never rendered by the app."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from google.api_core.exceptions import NotFound
from services.firebase import get_storage_bucket

MAX_CV_BYTES = 2 * 1024 * 1024
CV_RETENTION_DAYS = 30


class CvUnavailable(ValueError):
    pass


def expires_at(metadata, submitted_at=None):
    value = (metadata or {}).get('expiresAt')
    if value:
        try:
            result = datetime.fromisoformat(value)
            if result.tzinfo is None:
                raise ValueError('Missing timezone')
            return result
        except (TypeError, ValueError):
            raise CvUnavailable('This CV is no longer available.') from None
    if submitted_at:
        return submitted_at.replace(tzinfo=timezone.utc) + timedelta(days=CV_RETENTION_DAYS) if submitted_at.tzinfo is None else submitted_at + timedelta(days=CV_RETENTION_DAYS)
    return None


def available(metadata, submitted_at=None):
    if not metadata:
        return False
    try:
        deadline = expires_at(metadata, submitted_at)
        return deadline is None or datetime.now(timezone.utc) < deadline
    except CvUnavailable:
        return False



def full_name(value):
    if not isinstance(value, str):
        raise ValueError('Enter your full name.')
    name = ' '.join(value.split())
    if not name or len(name) > 200 or any(ord(c) < 32 for c in name):
        raise ValueError('Enter your full name (up to 200 characters).')
    return name


def read_cv(upload):
    if upload is None:
        raise ValueError('Upload your CV as a PDF (up to 2 MB).')
    data = upload.stream.read(MAX_CV_BYTES + 1)
    if not data or len(data) > MAX_CV_BYTES:
        raise ValueError('Choose a PDF no larger than 2 MB.')
    # File extension or browser MIME alone is not evidence of PDF content.
    if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-1024:]:
        raise ValueError('Choose a PDF file.')
    return data


def store_cv(application_id, data):
    digest = hashlib.sha256(data).hexdigest()
    path = f'hiring_cv/{application_id}/{digest}.pdf'
    blob = get_storage_bucket().blob(path)
    blob.upload_from_string(data, content_type='application/pdf', if_generation_match=0, timeout=30)
    return {'path': path, 'generation': str(blob.generation), 'sha256': digest, 'bytes': len(data), 'expiresAt': (datetime.now(timezone.utc) + timedelta(days=CV_RETENTION_DAYS)).isoformat()}


def download_cv(application_id, metadata):
    if not available(metadata):
        raise CvUnavailable('This CV has expired under the 30-day retention policy.')
    expected = f'hiring_cv/{application_id}/{metadata.get("sha256")}.pdf'
    if (metadata.get('path') != expected or not re.fullmatch(r'[0-9a-f]{64}', metadata.get('sha256', ''))
            or not str(metadata.get('generation', '')).isdigit()):
        raise ValueError('CV reference is invalid.')
    blob = get_storage_bucket().blob(expected, generation=int(metadata['generation']))
    try:
        data = blob.download_as_bytes(timeout=30)
    except NotFound:
        raise CvUnavailable('This CV is no longer available.') from None
    if len(data) > MAX_CV_BYTES or hashlib.sha256(data).hexdigest() != metadata['sha256']:
        raise ValueError('CV could not be verified.')
    return data


def cleanup_on_rollback(session, metadata):
    from sqlalchemy import event
    import logging
    def cleanup(_session):
        try:
            get_storage_bucket().blob(metadata['path'], generation=int(metadata['generation'])).delete(
                if_generation_match=int(metadata['generation']), timeout=10)
        except Exception:
            logging.getLogger(__name__).warning('CV rollback cleanup needs retry; no file URL logged')
    event.listen(session, 'after_rollback', cleanup, once=True)
