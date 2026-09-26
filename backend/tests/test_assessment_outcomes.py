from types import SimpleNamespace
import uuid

from services.assessment_outcomes import evaluate_assessment
from services.assessment_outcomes import normalize_criteria, allow_remaining_attempts
import pytest


def attempt(state='VERIFIED', score=82, *, technique_ok=True, product_ok=True):
    return SimpleNamespace(
        id=uuid.uuid4(), verification_state=state, authoritative_score=score,
        reconciliation={'reason': 'Recorded evidence explanation'},
        server_block={'product_half': {'ok': product_ok},
                      'verdict': {'technique_ok': technique_ok, 'summary': 'Result summary'}},
    )


def test_demonstrated_result_is_explainable_but_requires_human_without_validation(monkeypatch):
    monkeypatch.delenv('ASSESSMENT_EMPLOYMENT_VALIDATED', raising=False)
    result = evaluate_assessment(attempt())
    assert result['outcome'] == 'demonstrated'
    assert result['reasonCodes'] == ['profile_criteria_met']
    assert result['profile']['criteria']['minimumProductScore'] == 55
    assert result['workflowGate']['status'] == 'human_review_required'
    assert result['workflowGate']['automaticAdvancementEligible'] is False


def test_validated_profile_can_gate_only_gradeable_terminal_evidence(monkeypatch):
    monkeypatch.setenv('ASSESSMENT_EMPLOYMENT_VALIDATED', '1')
    passed = evaluate_assessment(attempt(score=55))
    missed = evaluate_assessment(attempt(score=54))
    retry = evaluate_assessment(attempt(state='INSUFFICIENT', score=None, product_ok=False))
    assert passed['workflowGate']['status'] == 'pass'
    assert passed['workflowGate']['automaticAdvancementEligible'] is True
    assert missed['workflowGate']['status'] == 'does_not_pass'
    assert missed['workflowGate']['automaticRejectionEligible'] is True
    assert retry['outcome'] == 'review_required'
    assert retry['workflowGate']['status'] == 'human_review_required'


def test_gradeable_wrong_technique_is_not_demonstrated():
    result = evaluate_assessment(attempt(state='INSUFFICIENT', score=None, technique_ok=False, product_ok=True))
    assert result['outcome'] == 'not_demonstrated'
    assert result['reasonCodes'] == ['requested_technique_not_demonstrated']


def test_unknown_profile_never_gates():
    result = evaluate_assessment(attempt(), profile_version='future-profile')
    assert result['outcome'] == 'review_required'
    assert result['reasonCodes'] == ['unknown_profile_version']


def test_customer_threshold_is_used_and_explained():
    result = evaluate_assessment(attempt(score=82), criteria={'minimumProductScore': 85})
    assert result['outcome'] == 'not_demonstrated'
    assert result['profile']['criteria']['minimumProductScore'] == 85
    assert '85' in result['explanation']
    assert evaluate_assessment(attempt(score=85), criteria={'minimumProductScore': 85})['outcome'] == 'demonstrated'


@pytest.mark.parametrize('criteria', [{'minimumProductScore': float('nan')}, {'minimumProductScore': 101},
    {'minimumProductScore': True}, {'age': 18}, {'requestedTechniqueRequired': False}, []])
def test_criteria_reject_unsupported_or_invalid_measures(criteria):
    with pytest.raises(ValueError):
        normalize_criteria(criteria)


def test_unused_attempts_prevent_automatic_rejection(monkeypatch):
    monkeypatch.setenv('ASSESSMENT_EMPLOYMENT_VALIDATED', '1')
    result = allow_remaining_attempts(evaluate_assessment(attempt(score=20)), 2)
    assert result['workflowGate']['status'] == 'retry_available'
    assert result['workflowGate']['automaticRejectionEligible'] is False


@pytest.mark.parametrize('score', [float('nan'), float('inf'), -1, 101, True])
def test_bad_server_numbers_never_pass(score):
    assert evaluate_assessment(attempt(score=score))['outcome'] == 'review_required'
