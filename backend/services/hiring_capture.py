"""Bounded, untrusted capture claims; never evidence of server verification."""
import copy

FIELDS = {'version', 'profile', 'recording', 'mirrored', 'sourceWidth', 'sourceHeight',
          'initialHand', 'countdownSec', 'detectorWidth', 'timing', 'modelAsset',
          'modelHashVerified', 'samples', 'durationMs', 'issues'}
ISSUES = {'geometry-changed', 'sample-limit', 'camera-restarted', 'recorder-error',
          'recording-unavailable', 'event-limit'}


def validate_capture(value):
    # Old recordings remain usable as provisional evidence, not certified media.
    if value is None:
        return None
    def require(condition):
        if not condition:
            raise ValueError('Invalid hiring capture metadata')
    def integer(number, low, high):
        return type(number) is int and low <= number <= high
    require(isinstance(value, dict))
    require(type(value.get('version')) is int and value['version'] in (1, 2))
    require(set(value) == (FIELDS | {'events'} if value['version'] == 2 else FIELDS))
    for key, expected in {'profile': 'knife-motion-v1',
                          'recording': 'camera-stream', 'mirrored': False,
                          'timing': 'performance-clock-approximate',
                          'modelAsset': 'hand_landmarker.task', 'modelHashVerified': False}.items():
        require(type(value[key]) is type(expected) and value[key] == expected)
    for key in ('sourceWidth', 'sourceHeight', 'detectorWidth'):
        require(integer(value[key], 1, 8192))
    require(value['initialHand'] in ('Left', 'Right'))
    require(integer(value['countdownSec'], 0, 30))
    require(integer(value['durationMs'], 1, 180000))
    issues = value['issues']
    require(isinstance(issues, list) and len(issues) <= len(ISSUES))
    require(all(isinstance(item, str) and item in ISSUES for item in issues))
    require(len(set(issues)) == len(issues))
    samples = value['samples']
    require(isinstance(samples, list) and len(samples) <= 6000)
    previous = -1
    for sample in samples:
        require(isinstance(sample, list) and len(sample) == 3)
        offset, elapsed, hand = sample
        require(integer(offset, 0, value['durationMs']) and offset > previous)
        require(integer(elapsed, 0, 180000) and hand in ('Left', 'Right'))
        previous = offset
    if value['version'] == 2:
        events = value['events']
        require(isinstance(events, list) and len(events) <= 128)
        previous = -1
        for event in events:
            require(isinstance(event, dict) and set(event) == {'type', 'offsetMs', 'hand'})
            require(event['type'] in ('session-reset', 'hand-change'))
            require(integer(event['offsetMs'], 0, value['durationMs']) and event['offsetMs'] >= previous)
            require(event['hand'] in ('Left', 'Right'))
            previous = event['offsetMs']
    return copy.deepcopy(value)


def bind_capture(claim, evidence):
    if claim is None:
        return None
    return {'trust': 'client-claim', 'serverVerified': False,
            'assessmentId': evidence['assessmentId'],
            'recordingGeneration': str(evidence['generation']),
            'sourceRecordingGeneration': evidence['metadata'].get('source_recording_generation'),
            'capture': copy.deepcopy(claim)}
