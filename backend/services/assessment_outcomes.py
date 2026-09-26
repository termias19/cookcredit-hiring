"""Versioned, explainable employment-work-sample outcomes.

The outcome is deliberately separate from the raw 0..100 score.  It is a small,
auditable ruleset over server-derived evidence and never makes the final hiring
decision.  Automatic employment gating stays disabled unless the deployment has
completed the relevant validation work and explicitly enables it.
"""
from __future__ import annotations

import os
import math
from services.skill_scoring import PASS_SCORE
from services.live_motion_evidence import VERSION, PROFILE_ID, normalize_motion_criteria, evaluate_live_motion, is_live_motion


PROFILES = {
    VERSION: {'profileId': PROFILE_ID, 'label': 'Knife work: rhythm, consistency and form'},
    'knife-dice-v1': {
        'profileId': 'guillotine_dice',
        'minimumProductScore': PASS_SCORE,
        'label': 'Basic guillotine dice',
    },
}


def normalize_criteria(value=None, *, skill_floor=None):
    """Only supported, server-measurable criteria may affect the assessment gate."""
    value = value if value is not None else {}
    if isinstance(value, dict) and value.get('profileVersion') == VERSION:
        return normalize_motion_criteria(value)
    if not isinstance(value, dict) or set(value) - {'minimumProductScore', 'requestedTechniqueRequired', 'gradeableProductRequired'}:
        raise ValueError('Unsupported assessment criteria')
    score = value.get('minimumProductScore', skill_floor if skill_floor is not None else PASS_SCORE)
    if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError('minimumProductScore must be a number from 0 to 100')
    for key in ('requestedTechniqueRequired', 'gradeableProductRequired'):
        if key in value and value[key] is not True:
            raise ValueError(f'{key} must remain enabled')
    return {'minimumProductScore': score, 'requestedTechniqueRequired': True, 'gradeableProductRequired': True}


def evaluate_assessment(attempt, *, profile_version: str = 'knife-dice-v1', criteria=None) -> dict:
    """Return a stable result with evidence, reasons, and the allowed workflow gate."""
    if profile_version == VERSION or is_live_motion(attempt) or (isinstance(criteria, dict) and criteria.get('profileVersion') == VERSION):
        return evaluate_live_motion(attempt, criteria)
    profile = PROFILES.get(profile_version)
    if profile is None:
        return _result(
            outcome='review_required', reason_codes=['unknown_profile_version'],
            explanation='This assessment profile version is not recognized. A person must review it.',
            profile_version=profile_version, profile=None, attempt=attempt,
        )
    try:
        configured = normalize_criteria(criteria)
    except ValueError:
        return _result(outcome='review_required', reason_codes=['invalid_criteria'],
                       explanation='The saved assessment criteria need review.',
                       profile_version=profile_version, profile=profile, attempt=attempt)
    profile = {**profile, **configured}
    if attempt is None:
        return _result(
            outcome='review_required', reason_codes=['no_completed_attempt'],
            explanation='No completed assessment evidence is available yet.',
            profile_version=profile_version, profile=profile, attempt=None,
        )

    state = str(getattr(attempt, 'verification_state', '') or '').upper()
    score = _number(getattr(attempt, 'authoritative_score', None))
    reconciliation = getattr(attempt, 'reconciliation', None) or {}
    server = getattr(attempt, 'server_block', None) or {}
    verdict = server.get('verdict') if isinstance(server.get('verdict'), dict) else {}
    product = server.get('product_half') if isinstance(server.get('product_half'), dict) else {}

    if state in {'PROVISIONAL', 'VERIFYING'}:
        return _result(
            outcome='review_required', reason_codes=['analysis_in_progress'],
            explanation='The recording is still being analyzed.',
            profile_version=profile_version, profile=profile, attempt=attempt,
        )
    if state == 'DISPUTED':
        return _result(
            outcome='review_required', reason_codes=['evidence_inconsistent'],
            explanation=reconciliation.get('reason') or 'The submitted claim and recording are inconsistent.',
            profile_version=profile_version, profile=profile, attempt=attempt,
        )
    if bool(product.get('ok')) and verdict.get('technique_ok') is False:
        return _result(
            outcome='not_demonstrated', reason_codes=['requested_technique_not_demonstrated'],
            explanation=verdict.get('summary') or 'The requested knife technique was not demonstrated.',
            profile_version=profile_version, profile=profile, attempt=attempt,
        )
    if state != 'VERIFIED' or score is None or not bool(product.get('ok')):
        reason = reconciliation.get('reason') or product.get('reason') or 'The recording could not be graded reliably.'
        return _result(
            outcome='review_required', reason_codes=['ungradeable_evidence'], explanation=reason,
            profile_version=profile_version, profile=profile, attempt=attempt,
        )
    if verdict.get('technique_ok') is not True:
        return _result(
            outcome='review_required', reason_codes=['technique_measurement_missing'],
            explanation='The requested-technique measurement is missing. A person must review the recording.',
            profile_version=profile_version, profile=profile, attempt=attempt,
        )
    if score < profile['minimumProductScore']:
        return _result(
            outcome='not_demonstrated', reason_codes=['product_score_below_profile_threshold'],
            explanation=(f"The gradeable product score was {score:g}; this profile's "
                         f"documented demonstration threshold is {profile['minimumProductScore']:g}."),
            profile_version=profile_version, profile=profile, attempt=attempt,
        )
    return _result(
        outcome='demonstrated', reason_codes=['profile_criteria_met'],
        explanation=(f"The requested technique was detected and the gradeable product score "
                     f"met the documented {profile['minimumProductScore']:g} threshold."),
        profile_version=profile_version, profile=profile, attempt=attempt,
    )


def _number(value):
    try:
        number = float(value) if value is not None and not isinstance(value, bool) else None
        return number if number is not None and math.isfinite(number) and 0 <= number <= 100 else None
    except (TypeError, ValueError):
        return None


def _result(*, outcome, reason_codes, explanation, profile_version, profile, attempt):
    validated = os.environ.get('ASSESSMENT_EMPLOYMENT_VALIDATED') == '1'
    if outcome == 'review_required' or not validated:
        gate = 'human_review_required'
        automatic = False
    else:
        gate = 'pass' if outcome == 'demonstrated' else 'does_not_pass'
        automatic = True
    score = _number(getattr(attempt, 'authoritative_score', None)) if attempt else None
    return {
        'outcome': outcome,
        'reasonCodes': reason_codes,
        'explanation': explanation,
        'profile': {
            'id': profile.get('profileId') if profile else None,
            'version': profile_version,
            'label': profile.get('label') if profile else None,
            'criteria': ({'minimumProductScore': profile['minimumProductScore'],
                          'requestedTechniqueRequired': True,
                          'gradeableProductRequired': True} if profile else None),
        },
        'evidence': {
            'attemptId': str(attempt.id) if attempt and getattr(attempt, 'id', None) else None,
            'verificationState': getattr(attempt, 'verification_state', None) if attempt else None,
            'authoritativeScore': score,
        },
        'workflowGate': {
            'status': gate,
            'automaticAdvancementEligible': automatic and outcome == 'demonstrated',
            'automaticRejectionEligible': automatic and outcome == 'not_demonstrated',
            'employmentValidated': validated,
            'humanDecisionRequired': not automatic,
        },
    }


def allow_remaining_attempts(result, remaining):
    """A candidate with unused retries must not be rejected by an automatic gate."""
    result['attemptsRemaining'] = max(0, remaining)
    if remaining > 0 and result['outcome'] == 'not_demonstrated':
        result['workflowGate'] = {**result['workflowGate'], 'status': 'retry_available',
                                  'automaticRejectionEligible': False, 'humanDecisionRequired': True}
    return result
