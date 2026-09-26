import json
from types import SimpleNamespace
import pytest
from services import engine_recording_import as importer
from services import engine_assessment


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status_code = status
        self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size):
        for pos in range(0, len(self.body), size): yield self.body[pos:pos+size]


class Blob:
    def __init__(self):
        self.metadata = None
        self.generation = None
        self.size = None
        self.content_type = None
        self.uploads = []
    def exists(self, **kwargs): return self.generation is not None
    def reload(self, **kwargs): pass
    def upload_from_file(self, file, **kwargs):
        assert kwargs['if_generation_match'] == 0
        self.uploads.append(file.read())
        self.size = kwargs['size']
        self.content_type = kwargs['content_type']
        self.generation = 9876


@pytest.fixture
def setup(monkeypatch):
    path = 'cookcredit-skill/users/alice/assessments/a1/recording.webm'
    record = {'userId': 'alice', 'assessmentId': 'a1', 'status': 'ready', 'mode': 'assessment',
              'storagePath': path, 'mimeType': 'video/webm', 'sizeBytes': 5,
              'consentEvidence': {'dataAndBiometric': True, 'age18Plus': True}}
    metadata = {'bucket': importer.SOURCE_BUCKET, 'name': path, 'generation': '123',
                'size': '5', 'contentType': 'video/webm',
                'metadata': {'ownerUid': 'alice', 'assessmentId': 'a1'}}
    blob, calls = Blob(), []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        if kwargs.get('params', {}).get('alt') == 'media':
            return Response(b'video', headers={'x-goog-generation': '123'})
        return Response(metadata)
    monkeypatch.setattr(importer.requests, 'get', get)
    monkeypatch.setattr(importer, 'get_storage_bucket', lambda: SimpleNamespace(name='private-hiring', blob=lambda _: blob))
    return record, metadata, blob, calls


def test_applicant_read_and_immutable_retry(setup):
    record, _, blob, calls = setup
    first = importer.import_owned_recording(record, 'alice', 'a1', id_token='private-id-token', app_check='attestation')
    second = importer.import_owned_recording(record, 'alice', 'a1', id_token='private-id-token', app_check='attestation')
    assert first == second and first[1:] == ('9876', 'video/webm', '123')
    assert first[0].startswith('cookcredit-skill/users/alice/assessments/import_')
    assert blob.uploads == [b'video']
    assert 'private-id-token' not in json.dumps(blob.metadata)
    assert all(options['allow_redirects'] is False for _, options in calls)
    assert all(options['headers']['Authorization'] == 'Firebase private-id-token' for _, options in calls)
    assert [options['params']['generation'] for _, options in calls if 'params' in options] == ['123']


@pytest.mark.parametrize('change', [
    {'bucket': 'other-bucket'}, {'name': 'cookcredit-skill/users/bob/assessments/a1/recording.webm'},
    {'size': '83886081'}, {'contentType': 'text/html'}, {'generation': ''},
    {'metadata': {'ownerUid': 'bob', 'assessmentId': 'a1'}},
])
def test_source_metadata_must_match_owned_record(setup, change):
    record, metadata, blob, _ = setup
    metadata.update(change)
    with pytest.raises(importer.EngineImportError):
        importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
    assert blob.uploads == []


@pytest.mark.parametrize('payload,generation', [(b'longer-than-five', '123'), (b'vid', '123'), (b'video', '124')])
def test_bad_media_never_reaches_private_destination(setup, monkeypatch, payload, generation):
    record, metadata, blob, _ = setup
    monkeypatch.setattr(importer.requests, 'get', lambda url, **opts:
        Response(payload, headers={'x-goog-generation': generation}) if 'params' in opts else Response(metadata))
    with pytest.raises(importer.EngineImportError):
        importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
    assert blob.uploads == []


def test_firestore_reads_use_applicant_identity_and_rules(monkeypatch):
    calls = []
    url = f'https://firestore.googleapis.com/v1/projects/{importer.SOURCE_PROJECT}/databases/(default)/documents/cookcreditSkill/alice/assessments/a1'
    def get(request_url, **kwargs):
        calls.append((request_url, kwargs))
        return Response({'name': url.split('/v1/')[1], 'fields': {
            'userId': {'stringValue': 'alice'}, 'score': {'integerValue': '81'},
            'consentEvidence': {'mapValue': {'fields': {'age18Plus': {'booleanValue': True}}}}}})
    monkeypatch.setattr(importer.requests, 'get', get)
    result = importer.read_owned_record('alice', 'a1', id_token='applicant', app_check='app')
    assert result == {'userId': 'alice', 'score': 81, 'consentEvidence': {'age18Plus': True}}
    assert calls[0][0] == url
    assert calls[0][1]['headers'] == {'Authorization': 'Bearer applicant', 'X-Firebase-AppCheck': 'app'}


def test_import_checks_consent_before_any_video_read(monkeypatch, setup):
    record, _, _, _ = setup
    record['consentEvidence']['dataAndBiometric'] = False
    monkeypatch.setenv('ENGINE_APPLICANT_IMPORT_ENABLED', '1')
    monkeypatch.setattr(importer, 'read_owned_record', lambda *a, **k: record)
    monkeypatch.setattr(importer, 'import_owned_recording', lambda *a, **k: pytest.fail('No video read allowed'))
    monkeypatch.setattr(engine_assessment, 'get_firestore_client', lambda: pytest.fail('No live admin access allowed'))
    with pytest.raises(engine_assessment.InvalidEngineAssessment):
        engine_assessment.verified_engine_assessment('alice', 'a1', id_token='applicant')


def test_redirect_cannot_receive_applicant_credentials(monkeypatch):
    monkeypatch.setattr(importer.requests, 'get', lambda *a, **k: Response({}, status=302))
    with pytest.raises(importer.EngineImportError):
        importer.read_owned_record('alice', 'a1', id_token='private-token')
