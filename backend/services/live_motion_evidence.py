"""Contract for the published wrist-motion assessment, separate from dice scoring.

The source library confirms ownership, consent and the recording generation. It
does not make the owner's writable browser measurements authoritative. Never
substitute the unrelated GPU product score for these axes.
"""
import math

VERSION = 'knife-motion-v1'
PROFILE_ID = 'wrist_motion'
FIELDS = {'minimumRhythm': 'rhythm', 'minimumConsistency': 'consistency', 'minimumForm': 'form'}
RANGE_FIELDS = {**FIELDS, 'minimumCadence': 'cadence'}
UPPER_FIELDS = {key.replace('minimum', 'maximum'): axis for key, axis in RANGE_FIELDS.items()}


def hiring_motion_criteria(value=None, *, skill_floor=None):
    """Normalize new hiring activity without reinterpreting historical product criteria."""
    if value is None or value == {}:
        if skill_floor is not None:
            raise ValueError('This role has legacy score criteria. Review its motion criteria before inviting applicants.')
        value = {'profileVersion': VERSION}
    return normalize_motion_criteria(value)


def normalize_motion_criteria(value):
    if not isinstance(value, dict) or set(value) - {'profileVersion', *RANGE_FIELDS, *UPPER_FIELDS}:
        raise ValueError('Unsupported live knife-assessment criteria')
    if value.get('profileVersion') != VERSION:
        raise ValueError('Unsupported live knife-assessment version')
    result = {'profileVersion': VERSION}
    for key, axis in {**RANGE_FIELDS, **UPPER_FIELDS}.items():
        if key not in value:
            continue
        score = value[key]
        maximum = 30 if axis == 'cadence' else 100
        if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= maximum:
            raise ValueError(f'{key} must be a number from 0 to {maximum}')
        result[key] = score
    for lower in RANGE_FIELDS:
        upper = lower.replace('minimum', 'maximum')
        if lower in result and upper in result and result[lower] > result[upper]:
            raise ValueError(f'{lower} must not exceed {upper}')
    return result


def _number(value, maximum=100):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and 0 <= value <= maximum else None


def motion_estimates(attempt):
    block = getattr(attempt, 'on_device_block', None) or {}
    block = block if isinstance(block, dict) else {}
    metrics = block.get('metrics') if isinstance(block.get('metrics'), dict) else {}
    return {
        'overall': _number(block.get('score')),
        **{field: _number(metrics.get(field)) for field in FIELDS.values()},
        'strokes': _number(block.get('strokes'), 10000),
        'cadence': _number(block.get('cadence'), 30),
        'source': 'published-browser-assessment', 'serverVerified': False,
        # Version 1's cloud serializer converts null axes to zero. A zero cannot
        # be distinguished from missing signal and must not become a failure.
        'zeroMayMeanUnavailable': True,
    }


def evaluate_live_motion(attempt, criteria=None):
    try:
        configured = normalize_motion_criteria(criteria or {'profileVersion': VERSION})
        reason = 'live_assessment_manual_review'
        explanation = ('The saved rhythm, consistency and form are browser estimates. '
                       'Independent score verification is not part of this assessment; review the recording before deciding.')
    except ValueError:
        configured = None
        reason = 'assessment_contract_mismatch'
        explanation = ('The configured product-score criteria do not match this published motion assessment. '
                       'Review the role criteria and recording; this result cannot pass or fail those criteria.')
    estimates = motion_estimates(attempt)
    return {
        'outcome': 'review_required', 'reasonCodes': [reason], 'explanation': explanation,
        'profile': {'id': PROFILE_ID, 'version': VERSION,
                    'label': 'Knife work: rhythm, consistency and form', 'criteria': configured},
        'evidence': {'attemptId': str(attempt.id) if attempt else None,
                     'verificationState': getattr(attempt, 'verification_state', None),
                     'authoritativeScore': None, 'deviceEstimates': estimates},
        'criteriaComparison': [{'measure': axis,
                                **({'minimum': configured[key]} if key in configured else {}),
                                **({'maximum': configured[key.replace('minimum', 'maximum')]}
                                   if key.replace('minimum', 'maximum') in configured else {}),
                                'observed': estimates[axis], 'status': 'unverified'}
                               for key, axis in RANGE_FIELDS.items() if configured and
                               (key in configured or key.replace('minimum', 'maximum') in configured)],
        'workflowGate': {'status': 'human_review_required', 'automaticAdvancementEligible': False,
                         'automaticRejectionEligible': False, 'employmentValidated': False,
                         'humanDecisionRequired': True},
    }


def is_live_motion(attempt):
    meta = getattr(attempt, 'metadata_', None) or {}
    return (getattr(attempt, 'profile_id', None) == PROFILE_ID
            or meta.get('source') == 'cookcredit-skill-live'
            or meta.get('assessment_profile_version') == VERSION)


def motion_report(attempt, criteria=None):
    estimates = motion_estimates(attempt)
    return {
        'attemptId': str(attempt.id), 'status': 'review-required', 'score': None, 'tier': None,
        'profileId': PROFILE_ID, 'profileVersion': VERSION,
        'recordedAt': attempt.created_at.isoformat() if attempt.created_at else None,
        'deviceEstimates': estimates, 'measurements': {axis: None for axis in FIELDS.values()},
        'outcome': evaluate_live_motion(attempt, criteria),
        'calculation': {
            'scoreSource': 'Published live assessment; not independently verified',
            'clientScoreUsedForHiring': False,
            'comparison': 'Rhythm measures timing steadiness; consistency measures stroke-depth steadiness; form measures vertical motion. Available axes use weights 45%, 30% and 25%.',
            'resultReason': 'The uploaded recording is available for review. These estimates do not certify knife skill, cut quality or food safety.',
        },
        'provenance': {'recordingGenerationPinned': bool((attempt.metadata_ or {}).get('recording_generation')),
                       'profileId': PROFILE_ID, 'scoringSchema': 'published-wrist-motion-v1',
                       'attemptEventsPreserved': True, 'measurementSource': estimates['source']},
        'limitations': {'employmentValidated': False, 'automaticHiringDecision': False,
                       'message': 'Review the recording. Browser estimates are not server-verified and cannot automatically advance or reject this applicant. A zero may indicate unavailable signal in the saved assessment.'},
    }
