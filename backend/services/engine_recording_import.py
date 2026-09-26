"""Import one applicant-selected recording using that applicant's Firebase token.

The hiring service never receives administrative access to the live library.
Source reads go through Firebase security rules; the destination is private and
generation-pinned. Tokens, download tokens and source documents are not persisted.
"""
import hashlib
import json
import os
import re
import tempfile
from urllib.parse import quote

import requests
from google.api_core.exceptions import PreconditionFailed
from services.assessment_media import MAX_VIDEO_BYTES, VIDEO_TYPES
from services.firebase import get_storage_bucket

ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
SOURCE_PROJECT = 'foodnlit-1123e'
SOURCE_BUCKET = 'foodnlit-1123e.firebasestorage.app'


class EngineImportError(ValueError):
    pass


def enabled():
    return os.environ.get('ENGINE_APPLICANT_IMPORT_ENABLED') == '1'


def _headers(id_token, app_check, *, storage=False):
    if not id_token or len(id_token) > 16384:
        raise EngineImportError('Sign in to your CookCredit account again.')
    headers = {'Authorization': ('Firebase ' if storage else 'Bearer ') + id_token}
    if app_check:
        if len(app_check) > 16384:
            raise EngineImportError('Account security token is invalid.')
        headers['X-Firebase-AppCheck'] = app_check
    return headers


def _json_get(url, headers):
    try:
        with requests.get(url, headers=headers, timeout=(5, 25), stream=True,
                          allow_redirects=False) as response:
            if response.status_code in (401, 403, 404):
                raise EngineImportError('This saved assessment is unavailable to your signed-in account.')
            if response.status_code != 200:
                raise EngineImportError('The private assessment library is temporarily unavailable.')
            data = bytearray()
            for chunk in response.iter_content(16384):
                data.extend(chunk)
                if len(data) > 256 * 1024:
                    raise EngineImportError('The saved assessment metadata is too large.')
            value = json.loads(data)
            if not isinstance(value, dict):
                raise EngineImportError('The saved assessment metadata is invalid.')
            return value
    except (requests.RequestException, ValueError) as exc:
        if isinstance(exc, EngineImportError):
            raise
        raise EngineImportError('The private assessment library is temporarily unavailable.') from None


def _value(field, depth=0):
    if not isinstance(field, dict) or depth > 4:
        return None
    for key in ('stringValue', 'booleanValue', 'timestampValue'):
        if key in field:
            return field[key]
    if 'integerValue' in field:
        return int(field['integerValue'])
    if 'doubleValue' in field:
        return float(field['doubleValue'])
    if 'mapValue' in field:
        return {k: _value(v, depth + 1) for k, v in field['mapValue'].get('fields', {}).items()}
    return None


def read_owned_record(owner_uid, assessment_id, *, id_token, app_check=None):
    if not ID.fullmatch(str(owner_uid or '')) or not ID.fullmatch(str(assessment_id or '')):
        raise EngineImportError('Invalid assessment reference.')
    path = f'cookcreditSkill/{owner_uid}/assessments/{assessment_id}'
    url = f'https://firestore.googleapis.com/v1/projects/{SOURCE_PROJECT}/databases/(default)/documents/{path}'
    document = _json_get(url, _headers(id_token, app_check))
    if document.get('name') != url.split('/v1/', 1)[1]:
        raise EngineImportError('The saved assessment reference did not match.')
    return {key: _value(value) for key, value in document.get('fields', {}).items()}


def import_owned_recording(record, owner_uid, assessment_id, *, id_token, app_check=None):
    """Call only after the finalized document and application consent are checked."""
    path = str(record.get('storagePath') or '')
    expected = f'cookcredit-skill/users/{owner_uid}/assessments/{assessment_id}/'
    if (not path.startswith(expected) or path[len(expected):] not in
            ('recording.mp4', 'recording.webm', 'recording.mov')):
        raise EngineImportError('The recording does not belong to this assessment.')
    url = f'https://firebasestorage.googleapis.com/v0/b/{SOURCE_BUCKET}/o/{quote(path, safe="")}'
    headers = _headers(id_token, app_check, storage=True)
    source = _json_get(url, headers)
    generation = str(source.get('generation') or '')
    try:
        size = int(source.get('size') or 0)
    except (ValueError, TypeError):
        size = 0
    kind = str(source.get('contentType') or '').split(';', 1)[0]
    if (source.get('bucket') != SOURCE_BUCKET or source.get('name') != path
            or not generation.isdigit() or kind not in VIDEO_TYPES
            or not 0 < size <= MAX_VIDEO_BYTES
            or record.get('mimeType') != kind or record.get('sizeBytes') != size):
        raise EngineImportError('The saved recording size, format or version is invalid.')
    source_metadata = source.get('metadata') or {}
    if source_metadata.get('ownerUid') != owner_uid or source_metadata.get('assessmentId') != assessment_id:
        raise EngineImportError('The saved recording ownership could not be verified.')

    # Same selected source generation always resolves to the same destination.
    # A later overwrite cannot silently replace the video behind an assessment.
    identity = hashlib.sha256(f'{SOURCE_BUCKET}/{path}#{generation}'.encode()).hexdigest()
    extension = path.rsplit('.', 1)[1]
    destination = f'cookcredit-skill/users/{owner_uid}/assessments/import_{identity}/recording.{extension}'
    bucket = get_storage_bucket()
    if bucket.name == SOURCE_BUCKET:
        raise EngineImportError('Hiring recording storage must be separate from the live library.')
    blob = bucket.blob(destination)
    metadata = {'ownerUid': owner_uid, 'assessmentId': assessment_id,
                'source': 'cookcredit-hiring-import', 'sourceIdentity': identity}
    if blob.exists(timeout=20):
        blob.reload(timeout=20)
        if blob.metadata != metadata or int(blob.size or 0) != size or blob.content_type != kind:
            raise EngineImportError('The existing private recording did not match this assessment.')
        return destination, str(blob.generation), kind, generation

    # Spool to disk beyond 4 MB rather than multiplying an 80 MB byte buffer per request.
    with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024) as recording:
        received = 0
        try:
            with requests.get(url, headers=headers, params={'alt': 'media', 'generation': generation},
                              timeout=(5, 60), stream=True, allow_redirects=False) as response:
                if response.status_code != 200:
                    raise EngineImportError('The selected recording could not be read.')
                actual_generation = response.headers.get('x-goog-generation')
                if actual_generation and actual_generation != generation:
                    raise EngineImportError('The recording changed. Please select it again.')
                for chunk in response.iter_content(256 * 1024):
                    received += len(chunk)
                    if received > size or received > MAX_VIDEO_BYTES:
                        raise EngineImportError('The recording exceeds its verified size.')
                    recording.write(chunk)
        except requests.RequestException:
            raise EngineImportError('The recording transfer was interrupted. Please retry.') from None
        if received != size:
            raise EngineImportError('The recording transfer was incomplete. Please retry.')
        # The Firebase endpoint may vary which generation headers it exposes.
        # Re-reading server metadata also detects any source replacement while
        # downloading; GCS generations are never reused.
        confirmed = _json_get(url, headers)
        if str(confirmed.get('generation')) != generation:
            raise EngineImportError('The recording changed. Please select it again.')
        recording.seek(0)
        blob.metadata = metadata
        try:
            blob.upload_from_file(recording, size=size, content_type=kind,
                                  if_generation_match=0, timeout=120, checksum='auto')
        except PreconditionFailed:
            # A concurrent retry won the immutable create; verify its identity.
            pass
    blob.reload(timeout=20)
    if (blob.metadata != metadata or int(blob.size or 0) != size
            or blob.content_type != kind or not blob.generation):
        raise EngineImportError('The imported recording could not be verified.')
    return destination, str(blob.generation), kind, generation
