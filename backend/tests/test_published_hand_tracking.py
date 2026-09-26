import pytest
from services.published_hand_tracking import PublishedHandTracker


def test_single_hand_overrides_label_then_continuity_overrides_label():
    tracker = PublishedHandTracker('Right')
    assert tracker.update(0, [[.1,.2]], ['Left'])['wrist'] == [.1,.2]
    assert tracker.update(.04, [[.8,.8],[.12,.22]], ['Right','Left'])['wrist'] == [.12,.22]


def test_first_label_match_and_missing_label_fallback():
    assert PublishedHandTracker('Right').update(0, [[.1,.2],[.8,.8]], ['Left','Right'])['wrist'] == [.8,.8]
    assert PublishedHandTracker('Right').update(0, [[.1,.2],[.8,.8]], ['',''])['wrist'] == [.1,.2]


def test_velocity_hold_is_bounded_and_expiration_does_not_move_anchor():
    tracker = PublishedHandTracker('Right')
    tracker.update(0, [[.1,.2]], ['Right'])
    tracker.update(.01, [[.4,.5]], ['Right'])
    held = tracker.update(.10, [], [])
    assert held['extrapolated'] is True
    assert held['wrist'] == pytest.approx([.6,.7])
    assert tracker.anchor == (.4,.5)
    assert tracker.update(.17, [], []) is None


def test_stationary_hold_and_no_hand_before_first_detection():
    tracker = PublishedHandTracker('Left')
    assert tracker.update(0, [], []) is None
    tracker.update(.01, [[.2,.3]], ['Right'])
    assert tracker.update(.05, [], []) == {'wrist':[.2,.3], 'extrapolated':True}


@pytest.mark.parametrize('time,wrists,labels', [
    (True, [], []), (float('nan'), [], []), (-1, [], []), (-.1, [], []), (181, [], []),
    (0, [[float('inf'),0]], ['Right']), (0, [[0,0]], []), (0, [[0,0]]*3, ['Right']*3),
])
def test_invalid_observations_do_not_advance_tracker(time, wrists, labels):
    tracker = PublishedHandTracker('Right')
    with pytest.raises(ValueError): tracker.update(time, wrists, labels)
    assert tracker.previous_time == -1
