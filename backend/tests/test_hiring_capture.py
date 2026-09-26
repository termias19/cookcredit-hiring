import copy
import pytest
from services.hiring_capture import validate_capture, bind_capture


def claim():
    return dict(version=1, profile='knife-motion-v1', recording='camera-stream',
                mirrored=False, sourceWidth=1920, sourceHeight=1080, initialHand='Right',
                countdownSec=3, detectorWidth=480, timing='performance-clock-approximate',
                modelAsset='hand_landmarker.task', modelHashVerified=False,
                samples=[[10, 12, 'Right'], [45, 47, 'Left']], durationMs=100, issues=[])


def test_binding_never_certifies_and_does_not_alias_client_data():
    source = claim()
    cleaned = validate_capture(source)
    evidence = dict(assessmentId='owned-id', generation='42', metadata={'source_recording_generation':'21'})
    bound = bind_capture(cleaned, evidence)
    source['samples'].clear()
    cleaned['samples'].clear()
    assert len(bound['capture']['samples']) == 2
    assert bound['recordingGeneration'] == '42'
    assert bound['sourceRecordingGeneration'] == '21'
    assert bound['serverVerified'] is False
    assert bound['trust'] == 'client-claim'
    assert validate_capture(None) is None


@pytest.mark.parametrize('key,value', [
    ('version', True), ('version', 3), ('modelHashVerified', True), ('mirrored', True),
    ('sourceWidth', 0), ('sourceHeight', 8193), ('durationMs', float('nan')),
    ('durationMs', 180001), ('issues', ['invented']), ('issues', [['unhashable']]),
    ('samples', [[101, 10, 'Right']]), ('samples', [[1, 1, 'Right'], [1, 2, 'Right']]),
    ('samples', [[True, 1, 'Right']]), ('samples', [[1, -1, 'Right']]),
    ('samples', [[1, 1, 'Other']]), ('samples', [[1, 1, 'Right']]*6001),
    ('recording', 'composite'), ('serverVerified', True),
])
def test_rejects_malformed_or_authority_claims(key, value):
    candidate = claim()
    candidate[key] = value
    with pytest.raises(ValueError):
        validate_capture(candidate)


def test_discontinuities_are_retained_as_unverified_claims():
    candidate = claim()
    candidate['issues'] = ['camera-restarted', 'geometry-changed']
    assert validate_capture(candidate)['issues'] == candidate['issues']


@pytest.mark.parametrize('events', [
    [{'type':'session-reset','offsetMs':20,'hand':'Right'}, {'type':'hand-change','offsetMs':30,'hand':'Left'}],
    [],
])
def test_version_two_retains_explicit_control_events(events):
    candidate = {**claim(), 'version':2, 'events':events}
    assert validate_capture(candidate) == candidate


@pytest.mark.parametrize('events', [
    [{'type':'unknown','offsetMs':20,'hand':'Right'}],
    [{'type':'hand-change','offsetMs':101,'hand':'Left'}],
    [{'type':'session-reset','offsetMs':True,'hand':'Right'}],
    [{'type':'hand-change','offsetMs':20,'hand':'Left'}]*129,
    [{'type':'hand-change','offsetMs':30,'hand':'Left'}, {'type':'session-reset','offsetMs':20,'hand':'Left'}],
])
def test_control_events_cannot_escape_timeline_bounds(events):
    with pytest.raises(ValueError): validate_capture({**claim(),'version':2,'events':events})
