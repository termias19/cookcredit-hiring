"""New partner request validation; historical scoring contracts stay readable."""
import pytest
from flask import Flask
from unittest.mock import Mock
from routes import partner


@pytest.mark.parametrize('body', [{}, {'assessmentCriteria':{}}, {'assessmentProfile':'wrist_motion'},
                                {'assessmentProfileVersion':'knife-motion-v1'},
                                {'assessmentCriteria':{'minimumRhythm':70,'minimumConsistency':60,'minimumForm':50}}])
def test_new_requests_default_to_published_motion(body):
    profile, version, criteria = partner._request_assessment(body)
    assert (profile, version) == ('wrist_motion', 'knife-motion-v1')
    assert criteria['profileVersion'] == version
    assert set(criteria) <= {'profileVersion','minimumRhythm','minimumConsistency','minimumForm'}
    if 'minimumRhythm' in body.get('assessmentCriteria', {}):
        assert criteria['minimumRhythm'] == 70


@pytest.mark.parametrize('body', [
    {'assessmentProfile':'guillotine_dice'}, {'assessmentProfileVersion':'knife-dice-v1'},
    {'assessmentProfile':'unknown'}, {'assessmentProfileVersion':''},
    {'assessmentCriteria':{'profileVersion':'knife-dice-v1'}},
    {'assessmentCriteria':{'minimumProductScore':70}}, {'assessmentCriteria':[]},
    {'assessmentCriteria':{'minimumRhythm':True}}, {'assessmentCriteria':{'minimumForm':101}},
])
def test_invalid_or_alternative_contracts_rejected_before_database(body, monkeypatch):
    database = Mock(side_effect=AssertionError('Must not persist an invalid request'))
    monkeypatch.setattr(partner, 'db_session', database)
    app = Flask(__name__)
    # Scope/auth is covered separately; exercise the HTTP handler's validation.
    app.add_url_rule('/request', view_func=partner.create_assessment_request.__wrapped__, methods=['POST'])
    response = app.test_client().post('/request', json=body)
    assert response.status_code == 400
    database.assert_not_called()


def test_implicit_and_explicit_motion_have_same_idempotency_contract():
    implicit = partner._request_assessment({})
    explicit = partner._request_assessment({'assessmentProfile':'wrist_motion',
        'assessmentProfileVersion':'knife-motion-v1','assessmentCriteria':{'profileVersion':'knife-motion-v1'}})
    assert implicit == explicit
    def fingerprint(contract):
        profile, version, criteria = contract
        return partner._fingerprint('assessment-requests', {'assessmentProfile':profile,
            'assessmentProfileVersion':version, 'assessmentCriteria':criteria})
    assert fingerprint(implicit) == fingerprint(explicit)
