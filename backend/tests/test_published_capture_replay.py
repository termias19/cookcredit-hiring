import math
import pytest
from services.published_capture_replay import replay_capture
from services.published_motion import score_motion_samples
from services.published_hand_tracking import PublishedHandTracker
from tests.test_hiring_capture import claim as base_claim


def case():
    claim = base_claim()
    claim.update(version=2, events=[], sourceWidth=640, sourceHeight=480,
                 countdownSec=0, initialHand='Right', durationMs=20000,
                 samples=[[i*40, i*40, 'Right'] for i in range(500)])
    observations = [{'offsetMs': i*40, 'wrists': [[.5,(240+60*math.sin(i*.45))/480]],
                     'labels': ['Right']} for i in range(500)]
    return claim, observations


def test_uninterrupted_replay_reuses_published_kernel():
    claim, observations = case()
    actual = replay_capture(claim, observations)
    expected = score_motion_samples([[i*.04,320,row['wrists'][0][1]*480]
                                     for i,row in enumerate(observations)])
    for key, value in expected.items():
        assert actual['metrics'][key] == pytest.approx(value) if value is not None else actual['metrics'][key] is None
    assert actual['serverVerified'] is False


def test_reset_removes_earlier_strokes_and_restarts_countdown():
    claim, observations = case()
    claim['events'] = [{'type':'session-reset','offsetMs':10000,'hand':'Right'}]
    claim['countdownSec'] = 1
    for sample in claim['samples'][250:]: sample[1] -= 10000
    actual = replay_capture(claim, observations)
    expected = score_motion_samples([[(row['offsetMs']-10000)/1000,320,row['wrists'][0][1]*480]
                                     for row in observations if row['offsetMs'] >= 11000])
    assert actual['metrics'] == expected


def test_trailing_reset_clears_result_without_another_frame():
    claim, observations = case()
    claim['events']=[{'type':'session-reset','offsetMs':19999,'hand':'Right'}]
    actual=replay_capture(claim, observations)
    assert actual['metrics']['strokes']==0
    assert actual['metrics']['overall'] is None


def test_hand_change_retains_strokes_but_resets_motion_windows():
    claim, observations=case()
    claim['events']=[{'type':'hand-change','offsetMs':19600,'hand':'Left'}]
    for sample in claim['samples'][490:]: sample[2]='Left'
    actual=replay_capture(claim,observations)
    assert actual['metrics']['strokes']>0
    assert actual['metrics']['form'] is None
    assert actual['metrics']['observedWindows']==0


def test_hand_change_retains_published_hold_state():
    tracker=PublishedHandTracker('Right')
    tracker.update(0,[[.1,.2]],['Right'])
    tracker.change_hand('Left')
    assert tracker.anchor is None
    assert tracker.update(.04,[],[]) == {'wrist':[.1,.2],'extrapolated':True}


def test_reset_clock_preserves_published_negative_hold_delta():
    tracker=PublishedHandTracker('Right')
    tracker.update(1,[[.1,.2]],['Right'],session_time_sec=1)
    tracker.update(2,[[.2,.3]],['Right'],session_time_sec=2)
    assert tracker.update(3,[],[],session_time_sec=0)['extrapolated'] is True


@pytest.mark.parametrize('damage',['missing-event','missing-observation','offset-mismatch','issue','old-version'])
def test_incomplete_or_contradictory_inputs_fail_closed(damage):
    claim, observations=case()
    if damage=='missing-event': claim['samples'][10][2]='Left'
    elif damage=='missing-observation': observations.pop()
    elif damage=='offset-mismatch': observations[0]['offsetMs']=1
    elif damage=='issue': claim['issues']=['camera-restarted']
    else: claim['version']=1;claim.pop('events')
    with pytest.raises(ValueError): replay_capture(claim,observations)


def test_actual_published_control_and_scoring_reference():
    import json
    from pathlib import Path
    references=json.loads((Path(__file__).parent/'fixtures/published_motion/control-golden.json').read_text())
    for reference in references['cases']:
        name=reference['name'];c,o=case()
        if name=='countdown':c['countdownSec']=3
        if name in ('swap','two-swaps-between-frames'):
            c['events']=[{'type':'hand-change','offsetMs':10000,'hand':'Left'}]
            if name=='swap':
                for sample in c['samples'][250:]:sample[2]='Left'
            else:c['events'].append({'type':'hand-change','offsetMs':10000,'hand':'Right'})
        if name in ('reset','reset-with-dropout'):
            c['events']=[{'type':'session-reset','offsetMs':10000,'hand':'Right'}]
            for sample in c['samples'][250:]:sample[1]-=10000
        if name.startswith('trailing'):
            c['events']=[{'type':'hand-change' if name.endswith('swap') else 'session-reset',
                          'offsetMs':19999,'hand':'Left' if name.endswith('swap') else 'Right'}]
        if name in ('dropouts','reset-with-dropout'):
            for index in list(range(100,110))+list(range(250,257)):
                o[index]['wrists']=[];o[index]['labels']=[]
        actual=replay_capture(c,o)['metrics']
        for key,expected in reference['expected'].items():
            if expected is None:assert actual[key] is None,(name,key)
            else:assert actual[key]==pytest.approx(expected,abs=1e-8),(name,key)

@pytest.mark.parametrize('damage', ['clock-jump','hand-reset-clock','same-hand-event','reset-clock'])
def test_contradictory_clock_or_control_claims_are_rejected(damage):
    c,o=case()
    if damage=='clock-jump':
        c['samples'][20][1]+=50
    elif damage=='hand-reset-clock':
        c['events']=[{'type':'hand-change','offsetMs':10000,'hand':'Left'}]
        for sample in c['samples'][250:]:sample[2]='Left';sample[1]-=10000
    elif damage=='same-hand-event':
        c['events']=[{'type':'hand-change','offsetMs':10000,'hand':'Right'}]
    else:
        c['events']=[{'type':'session-reset','offsetMs':10000,'hand':'Right'}]
    with pytest.raises(ValueError):replay_capture(c,o)
