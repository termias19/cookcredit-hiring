from scripts.hiring_read_load import assessment_request_body
from routes.partner import _request_assessment


def test_load_request_is_accepted_by_current_assessment_contract():
    body = assessment_request_body('load-regression', 0)
    profile, version, criteria = _request_assessment(body)
    assert profile == 'wrist_motion'
    assert version == 'knife-motion-v1'
    assert criteria == {'profileVersion':'knife-motion-v1','minimumRhythm':75}
    assert body['environment'] == 'test'
    assert body['candidateEmail'].endswith('@example.test')


def test_load_retry_identity_is_stable_and_create_identity_is_distinct():
    first = assessment_request_body('load-regression', 0)
    assert first == assessment_request_body('load-regression', 0)
    second = assessment_request_body('load-regression', 1)
    assert first['candidateEmail'] != second['candidateEmail']
    assert first['externalCandidateId'] != second['externalCandidateId']
    assert first['externalJobId'] == second['externalJobId']
