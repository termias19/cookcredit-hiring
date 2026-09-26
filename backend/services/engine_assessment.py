"""Verify a finalized record produced by the unchanged CookCredit Skill site."""
import re
from urllib.parse import quote

from services.firebase import get_firestore_client, STORAGE_BUCKET
from services.assessment_media import inspect_recording, InvalidRecording
from services import engine_recording_import

ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


class InvalidEngineAssessment(ValueError):
    pass


def verified_engine_assessment(owner_uid, assessment_id, *, id_token=None, app_check=None):
    if not ID_RE.fullmatch(str(owner_uid or '')) or not ID_RE.fullmatch(str(assessment_id or '')):
        raise InvalidEngineAssessment('Invalid assessment reference')
    importing = engine_recording_import.enabled()
    if importing:
        try:
            record = engine_recording_import.read_owned_record(
                owner_uid, assessment_id, id_token=id_token, app_check=app_check)
        except engine_recording_import.EngineImportError as exc:
            raise InvalidEngineAssessment(str(exc)) from None
    else:
        snapshot = (get_firestore_client().collection('cookcreditSkill').document(owner_uid)
                    .collection('assessments').document(assessment_id).get())
        if not snapshot.exists:
            raise InvalidEngineAssessment('Assessment was not found')
        record = snapshot.to_dict() or {}
    expected = f'cookcredit-skill/users/{owner_uid}/assessments/{assessment_id}/'
    if (record.get('userId') != owner_uid or record.get('assessmentId') != assessment_id
            or record.get('status') != 'ready' or record.get('mode') != 'assessment'
            or not str(record.get('storagePath') or '').startswith(expected)):
        raise InvalidEngineAssessment('Assessment is not a finalized owned assessment')
    evidence = record.get('consentEvidence') or {}
    if evidence.get('dataAndBiometric') is not True or evidence.get('age18Plus') is not True:
        raise InvalidEngineAssessment('Assessment consent evidence is incomplete')
    path = record['storagePath']
    source_generation = None
    try:
        if importing:
            path, generation, content_type, source_generation = engine_recording_import.import_owned_recording(
                record, owner_uid, assessment_id, id_token=id_token, app_check=app_check)
        else:
            locator = f'https://firebasestorage.googleapis.com/v0/b/{STORAGE_BUCKET}/o/{quote(path, safe="")}'
            inspected_path, generation, content_type = inspect_recording(locator, owner_uid)
            if inspected_path != path:
                raise InvalidEngineAssessment('Assessment recording path did not match')
    except (InvalidRecording, engine_recording_import.EngineImportError) as exc:
        raise InvalidEngineAssessment(str(exc)) from exc
    locator = f'https://firebasestorage.googleapis.com/v0/b/{STORAGE_BUCKET}/o/{quote(path, safe="")}'
    return {
        'assessmentId': assessment_id,
        'locator': locator,
        'storagePath': path,
        'generation': generation,
        'contentType': content_type,
        'onDevice': {
            'score': record.get('score'), 'grade': record.get('grade'),
            'strokes': record.get('strokes'), 'cadence': record.get('cadence'),
            'metrics': record.get('metrics') if isinstance(record.get('metrics'), dict) else {},
        },
        'metadata': {
            'tier': record.get('skillLevel'), 'angle': record.get('cameraAngle'),
            'cut': record.get('cutting'), 'duration_sec': record.get('durationSec'),
            'schema': f"engine-cloud-{record.get('schemaVersion', 'unknown')}",
            'source_recording_generation': source_generation,
        },
    }
