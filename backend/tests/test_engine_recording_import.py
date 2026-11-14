import json
from types import SimpleNamespace
import pytest
from services import engine_recording_import as importer
from services import engine_assessment
from datetime import datetime, timezone


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
        self.time_created = datetime(2026, 11, 13, tzinfo=timezone.utc)
    def exists(self, **kwargs): return self.generation is not None
    def reload(self, **kwargs): pass
    def open(self, mode, **kwargs):
        assert mode == 'wb' and kwargs['if_generation_match'] == 0
        assert kwargs['chunk_size'] == 1024 * 1024 and kwargs['checksum'] == 'crc32c'
        blob = self
        class Writer:
            def __init__(self): self.data = bytearray()
            def __enter__(self): return self
            def write(self, data): self.data.extend(data)
            def __exit__(self, kind, error, trace):
                if kind is None:
                    blob.uploads.append(bytes(self.data))
                    blob.size = len(self.data)
                    blob.content_type = kwargs['content_type']
                    blob.generation = 9876
        return Writer()


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


def test_retry_retains_creation_time_and_expiry_instead_of_extending_policy(setup):
    record, _, blob, _ = setup
    first, second = {}, {}
    importer.import_owned_recording(record, 'alice', 'a1', id_token='private', observation=first)
    importer.import_owned_recording(record, 'alice', 'a1', id_token='private', observation=second)
    assert first['generation'] == second['generation'] == '9876'
    assert first['createdAt'] == second['createdAt'] == '2026-11-13T00:00:00+00:00'
    assert first['expiresAt'] == second['expiresAt'] == '2026-12-13T00:00:00+00:00'
    assert len(blob.uploads) == 1


def test_failed_source_checksum_does_not_finalize_an_object(setup):
    record, metadata, blob, _ = setup
    metadata['md5Hash'] = 'INVALID_CHECKSUM'
    with pytest.raises(importer.EngineImportError, match='checksum'):
        importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
    assert blob.uploads == [] and blob.generation is None


def test_source_overwrite_before_final_chunk_does_not_publish_media(setup, monkeypatch):
    record, metadata, blob, _ = setup
    reads = 0
    def read(*args, **kwargs):
        nonlocal reads
        reads += 1
        return {**metadata, 'generation': '124' if reads == 2 else '123'}
    monkeypatch.setattr(importer, '_json_get', read)
    with pytest.raises(importer.EngineImportError, match='changed'):
        importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
    assert blob.uploads == [] and blob.generation is None


def test_interrupted_stream_is_cancelled_and_same_import_can_retry(setup, monkeypatch):
    record, _, blob, _ = setup
    normal = importer.requests.get
    def get(url, **options):
        response = normal(url, **options)
        if 'params' in options:
            def chunks(size):
                yield b'vi'
                raise importer.requests.ConnectionError('PRIVATE_TOKEN')
            response.iter_content = chunks
        return response
    monkeypatch.setattr(importer.requests, 'get', get)
    with pytest.raises(importer.EngineImportError, match='interrupted'):
        importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
    assert blob.uploads == []
    monkeypatch.setattr(importer.requests, 'get', normal)
    importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
    assert blob.uploads == [b'video']


def test_transfer_gate_rejects_excess_work_without_reading_or_losing_permits(setup):
    record, _, blob, calls = setup
    assert importer._import_gate.acquire(blocking=False)
    assert importer._import_gate.acquire(blocking=False)
    try:
        with pytest.raises(importer.EngineImportBusy):
            importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
        assert calls == [] and blob.uploads == []
    finally:
        importer._import_gate.release(); importer._import_gate.release()
    importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
    assert blob.uploads == [b'video']


def test_maximum_size_import_uses_real_sdk_buffer_with_bounded_python_memory(setup, monkeypatch):
    import tracemalloc
    from google.cloud.storage.fileio import BlobWriter
    record, metadata, blob, _ = setup
    size = importer.MAX_VIDEO_BYTES
    record['sizeBytes'] = size; metadata['size'] = str(size)
    blob.bucket = SimpleNamespace(client=object())
    transferred = 0
    class Upload:
        def transmit_next_chunk(self, transport, **options):
            nonlocal transferred
            data = self.stream.read(importer.UPLOAD_CHUNK_BYTES)
            transferred += len(data)
            if len(data) < importer.UPLOAD_CHUNK_BYTES:
                blob.size = transferred; blob.generation = 9876; blob.content_type = 'video/webm'
    def initiate(client, stream, kind, total, **options):
        assert total is None and options['if_generation_match'] == 0
        upload = Upload(); upload.stream = stream
        return upload, SimpleNamespace()
    blob._initiate_resumable_upload = initiate
    blob.open = lambda mode, **options: BlobWriter(blob, **options)
    class Media(Response):
        def iter_content(self, chunk):
            assert chunk == importer.TRANSFER_CHUNK_BYTES
            block = b'x' * chunk
            for offset in range(0, size, chunk): yield block
    monkeypatch.setattr(importer.requests, 'get', lambda url, **options:
        Media(b'', headers={'x-goog-generation': '123'}) if 'params' in options else Response(metadata))
    tracemalloc.start()
    try:
        result = importer.import_owned_recording(record, 'alice', 'a1', id_token='token')
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result[1] == '9876' and transferred == size
    assert peak < 12 * 1024 * 1024  # Python allocations, not total native/container RSS.
