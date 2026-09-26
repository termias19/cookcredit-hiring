from types import SimpleNamespace
import pytest

from services import engine_assessment


class Document:
    def __init__(self, record):
        self.record = record
    def collection(self, *_):
        return self
    def document(self, *_):
        return self
    def get(self):
        return SimpleNamespace(exists=self.record is not None,
                               to_dict=lambda: self.record)


def valid_record():
    return {
        'userId': 'alice', 'assessmentId': 'assessment_1', 'status': 'ready',
        'mode': 'assessment',
        'storagePath': 'cookcredit-skill/users/alice/assessments/assessment_1/recording.webm',
        'consentEvidence': {'dataAndBiometric': True, 'age18Plus': True},
        'score': 81, 'metrics': {'rhythm': 80}, 'schemaVersion': 2,
    }


def test_finalized_engine_record_is_verified_server_side(monkeypatch):
    record = valid_record()
    monkeypatch.setattr(engine_assessment, 'get_firestore_client', lambda: Document(record))
    monkeypatch.setattr(engine_assessment, 'inspect_recording',
                        lambda locator, uid: (record['storagePath'], '123', 'video/webm'))
    result = engine_assessment.verified_engine_assessment('alice', 'assessment_1')
    assert result['generation'] == '123'
    assert result['onDevice']['score'] == 81
    assert result['metadata']['schema'] == 'engine-cloud-2'
    assert result['storagePath'].startswith('cookcredit-skill/users/alice/')


@pytest.mark.parametrize('change', [
    {'userId': 'bob'}, {'status': 'upload-authorized'}, {'mode': 'practice'},
    {'storagePath': 'cookcredit-skill/users/bob/assessments/assessment_1/recording.webm'},
    {'consentEvidence': {'dataAndBiometric': False, 'age18Plus': True}},
])
def test_unowned_unfinished_or_unconsented_engine_record_is_rejected(monkeypatch, change):
    record = {**valid_record(), **change}
    monkeypatch.setattr(engine_assessment, 'get_firestore_client', lambda: Document(record))
    monkeypatch.setattr(engine_assessment, 'inspect_recording', lambda *a: pytest.fail('storage must not be read'))
    with pytest.raises(engine_assessment.InvalidEngineAssessment):
        engine_assessment.verified_engine_assessment('alice', 'assessment_1')
