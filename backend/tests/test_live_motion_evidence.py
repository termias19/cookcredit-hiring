from types import SimpleNamespace
import pytest
from services.assessment_outcomes import evaluate_assessment, normalize_criteria
from services.live_motion_evidence import motion_estimates, motion_report


def attempt(**kwargs):
    data = dict(id='sample', profile_id='wrist_motion', verification_state='VERIFIED',
                authoritative_score=99, server_block={'verdict': {'product_score': .99}},
                on_device_block={'score': 90, 'metrics': {'rhythm': 95, 'consistency': 88, 'form': 0}},
                metadata_={'source': 'cookcredit-skill-live', 'recording_generation': '123'}, created_at=None)
    return SimpleNamespace(**{**data, **kwargs})


def test_live_measurements_never_inherit_an_unrelated_product_gate(monkeypatch):
    monkeypatch.setenv('ASSESSMENT_EMPLOYMENT_VALIDATED', '1')
    result = evaluate_assessment(attempt(), criteria={'minimumProductScore': 55})
    assert result['outcome'] == 'review_required'
    assert result['reasonCodes'] == ['assessment_contract_mismatch']
    assert result['evidence']['authoritativeScore'] is None
    assert result['workflowGate']['automaticAdvancementEligible'] is False
    assert result['workflowGate']['automaticRejectionEligible'] is False


def test_live_axes_and_configured_criteria_are_explicit_but_provisional():
    criteria = {'profileVersion': 'knife-motion-v1', 'minimumRhythm': 80, 'minimumForm': 70}
    result = evaluate_assessment(attempt(), profile_version='knife-motion-v1', criteria=criteria)
    assert result['profile']['criteria'] == criteria
    assert result['criteriaComparison'][0] == {'measure': 'rhythm', 'minimum': 80, 'observed': 95, 'status': 'unverified'}
    assert result['criteriaComparison'][1]['status'] == 'unverified'
    report = motion_report(attempt(), criteria)
    assert report['score'] is None
    assert report['deviceEstimates']['rhythm'] == 95
    assert report['deviceEstimates']['zeroMayMeanUnavailable'] is True
    assert 'productScore' not in report['measurements']
    assert report['provenance']['recordingGenerationPinned'] is True


@pytest.mark.parametrize('value', [True, -1, 101, float('nan'), float('inf'), '75'])
def test_motion_criteria_reject_non_finite_and_non_numeric_values(value):
    with pytest.raises(ValueError):
        normalize_criteria({'profileVersion': 'knife-motion-v1', 'minimumRhythm': value})


def test_mixed_profiles_cannot_be_misinterpreted_as_motion_criteria():
    with pytest.raises(ValueError):
        normalize_criteria({'profileVersion': 'knife-motion-v1', 'minimumProductScore': 70})
    estimates = motion_estimates(attempt(on_device_block={'metrics': {'form': True, 'rhythm': '95', 'consistency': float('nan')}}))
    assert estimates['form'] is estimates['rhythm'] is estimates['consistency'] is None


@pytest.mark.parametrize('axis,limit', [('Rhythm',100),('Consistency',100),('Form',100),('Cadence',30)])
def test_metric_ranges_preserve_both_bounds_without_automatic_decisions(axis, limit):
    criteria = {'profileVersion':'knife-motion-v1', 'minimum'+axis:0, 'maximum'+axis:limit}
    assert normalize_criteria(criteria) == criteria
    result = evaluate_assessment(attempt(), criteria=criteria)
    comparison = result['criteriaComparison'][0]
    assert comparison['minimum'] == 0 and comparison['maximum'] == limit
    assert comparison['status'] == 'unverified'
    assert result['workflowGate']['automaticRejectionEligible'] is False
    assert result['workflowGate']['automaticAdvancementEligible'] is False
    assert normalize_criteria({'profileVersion':'knife-motion-v1', 'maximum'+axis:limit})['maximum'+axis] == limit
    for low, high in [(10,9), (0,limit+1), (0,True), (0,float('nan'))]:
        with pytest.raises(ValueError):
            normalize_criteria({'profileVersion':'knife-motion-v1','minimum'+axis:low,'maximum'+axis:high})


def test_manual_review_is_available_without_promising_independent_verification():
    report = motion_report(attempt())
    assert report['status'] == 'review-required'
    assert report['outcome']['reasonCodes'] == ['live_assessment_manual_review']
    assert report['deviceEstimates']['overall'] == 90
    assert report['deviceEstimates']['serverVerified'] is False
    assert report['score'] is None
    assert 'pending' not in report['calculation']['scoreSource'].lower()
    assert report['outcome']['workflowGate']['humanDecisionRequired'] is True
    assert report['outcome']['workflowGate']['automaticAdvancementEligible'] is False
    assert report['outcome']['workflowGate']['automaticRejectionEligible'] is False
