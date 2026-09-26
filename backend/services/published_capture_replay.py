"""Replay independent hand detections using published capture control semantics.

Capture clocks and controls remain client claims. Replaying them is diagnostic,
not sufficient to certify the claimed score or establish recording authenticity.
"""
from services.hiring_capture import validate_capture
from services.published_hand_tracking import PublishedHandTracker
from services.published_motion import score_motion_samples, summarize_motion


def replay_capture(capture, observations):
    claim = validate_capture(capture)
    if claim is None or claim['version'] != 2:
        raise ValueError('Explicit version 2 control events are required')
    if claim['issues']:
        raise ValueError('Capture issues must be resolved before replay')
    if not isinstance(observations, (list, tuple)) or len(observations) != len(claim['samples']):
        raise ValueError('One independent observation per capture sample is required')
    tracker = PublishedHandTracker(claim['initialHand'])
    events = iter(claim['events'])
    event = next(events, None)
    segments = [[]]
    held = missing = 0
    origin = None
    reset_offset = None
    for sample, observation in zip(claim['samples'], observations):
        offset, elapsed, hand = sample
        while event is not None and event['offsetMs'] <= offset:
            if event['type'] == 'hand-change':
                # swapHand clears detector/motion but preserves collected strokes.
                if event['hand'] == tracker.hand:
                    raise ValueError('Hand-change event did not change the selected hand')
                tracker.change_hand(event['hand'])
                segments.append([])
            else:
                # resetSession clears strokes/detector/motion. It does NOT clear
                # knifeAnchor or holdWrist/holdT in the published application.
                if event['hand'] != tracker.hand:
                    raise ValueError('Reset event contradicts selected hand')
                segments = [[]]
                origin = None
                reset_offset = event['offsetMs']
            event = next(events, None)
        if hand != tracker.hand:
            raise ValueError('Capture hand does not match explicit control events')
        sample_origin = offset-elapsed
        if reset_offset is not None and not reset_offset-1 <= sample_origin <= offset:
            raise ValueError('Capture clock does not match the explicit reset')
        # Both clocks are rounded to milliseconds in HiringCapture.sample.
        # Their difference can vary by at most two milliseconds without a reset.
        if origin is not None and abs(sample_origin-origin) > 2:
            raise ValueError('Capture clock changed without a session reset')
        if origin is None:
            origin = sample_origin
        if not isinstance(observation, dict) or set(observation) != {'offsetMs', 'wrists', 'labels'}:
            raise ValueError('Independent observation has an invalid shape')
        if type(observation['offsetMs']) is not int or observation['offsetMs'] != offset:
            raise ValueError('Independent observation does not match capture time')
        point = tracker.update(offset/1000, observation['wrists'], observation['labels'],
                               session_time_sec=elapsed/1000)
        if point is None:
            missing += 1
        else:
            held += int(point['extrapolated'])
            if elapsed >= claim['countdownSec']*1000:
                x, y = point['wrist']
                segments[-1].append([elapsed/1000, x*claim['sourceWidth'], y*claim['sourceHeight']])
    # A final control event can clear the displayed result even if no subsequent
    # inference frame was recorded. Do not silently drop these trailing events.
    while event is not None:
        if event['type'] == 'session-reset':
            if event['hand'] != tracker.hand:
                raise ValueError('Reset event contradicts selected hand')
            segments = [[]]
        else:
            if event['hand'] == tracker.hand:
                raise ValueError('Hand-change event did not change the selected hand')
            tracker.change_hand(event['hand']); segments.append([])
        event = next(events, None)
    scores = [score_motion_samples(segment) for segment in segments]
    times = [t for score in scores for t in score['strokeTimes']]
    amplitudes = [a for score in scores for a in score['strokeAmplitudes']]
    final = scores[-1]
    result = summarize_motion(times, amplitudes, final['observedWindows'],
                              final['activeWindows'], final['choppingWindows'])
    return {'schema': 'published-capture-replay-v1', 'serverVerified': False,
            'scope': 'Independent detections replayed against untrusted capture timing and controls',
            'metrics': result, 'inferenceSamples': len(observations),
            'heldSamples': held, 'missingSamples': missing,
            'scoredSamples': sum(map(len, segments))}
