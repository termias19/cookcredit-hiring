"""Original client capture for visual replay only, never verified score evidence."""
import gzip
import hashlib
import json
import math
from datetime import timedelta
from services.firebase import get_storage_bucket
from services.storage_signing import signed_url
from services.assessment_media import PLAYBACK_TTL_SECONDS
from google.api_core.exceptions import PreconditionFailed

MAX_BYTES = 4 * 1024 * 1024

def validate_landmarks(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != ({'version', 'timebase', 'mirrored', 'frames', 'renderer'} if value.get('version') == 2 else {'version', 'timebase', 'mirrored', 'frames'}):
        raise ValueError('Invalid original landmark capture')
    if type(value['version']) is not int or value['version'] not in (1, 2) or value['timebase'] != 'recording-ms' or value['mirrored'] is not False:
        raise ValueError('Unsupported original landmark capture')
    if value['version'] == 2 and (not isinstance(value.get('renderer'),str) or len(value['renderer']) != 64 or any(c not in '0123456789abcdef' for c in value['renderer'])):
        raise ValueError('Invalid engine renderer identity')
    frames = value['frames']
    if not isinstance(frames, list) or not 1 <= len(frames) <= 1900:
        raise ValueError('Invalid landmark frame count')
    previous = -1
    for row in frames:
        if not isinstance(row, list) or len(row) != (4 if value['version'] == 2 else 3):
            raise ValueError('Invalid landmark frame')
        t = row[0]
        if type(t) is not int or not previous < t <= 120000:
            raise ValueError('Invalid landmark timestamp')
        previous = t
        for hand in row[1:3]:
            if hand is None:
                continue
            if not isinstance(hand, list) or len(hand) != 21:
                raise ValueError('Invalid landmark hand')
            for point in hand:
                if not isinstance(point, list) or len(point) != 2 or any(
                    type(n) not in (int, float) or not math.isfinite(n) or not -1 <= n <= 2 for n in point):
                    raise ValueError('Invalid landmark coordinate')
        if value['version'] == 2:
            visual = row[3]
            keys = {'width','height','bladeExtendK','knifePresent','knifeConf','knifeWorker','bladeTrail'}
            if not isinstance(visual,dict) or set(visual)!=keys: raise ValueError('Invalid engine overlay')
            def number(n,low,high): return type(n) in (int,float) and math.isfinite(n) and low<=n<=high
            if any(type(visual[k]) is not int or not 1<=visual[k]<=8192 for k in ('width','height')): raise ValueError('Invalid overlay dimensions')
            if not number(visual['bladeExtendK'],0.1,20) or not number(visual['knifeConf'],0,1): raise ValueError('Invalid knife overlay')
            if any(type(visual[k]) is not bool for k in ('knifePresent','knifeWorker')): raise ValueError('Invalid knife state')
            trail=visual['bladeTrail']
            if not isinstance(trail,list) or len(trail)>48 or any(not isinstance(p,list) or len(p)!=2 or any(not number(n,-163840,163840) for n in p) for p in trail): raise ValueError('Invalid knife trail')
    raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError('Original landmark capture is too large')
    return raw

def save_landmarks(raw, evidence, owner):
    # Path comes only from already validated owned recording evidence.
    recording = evidence['storagePath']
    generation = str(evidence['generation'])
    digest = hashlib.sha256(raw).hexdigest()
    path = recording.rsplit('/', 1)[0] + '/landmarks-' + generation + '-' + digest + '.json'
    blob = get_storage_bucket().blob(path)
    blob.content_encoding = 'gzip'
    blob.cache_control = 'private, no-store'
    blob.metadata = {'ownerUid': owner, 'recordingGeneration': generation, 'sha256': digest}
    try:
        blob.upload_from_string(gzip.compress(raw, mtime=0), content_type='application/json',
                                if_generation_match=0, timeout=30)
    except PreconditionFailed:
        blob.reload(timeout=30)
        if blob.metadata != {'ownerUid': owner, 'recordingGeneration': generation, 'sha256': digest}:
            raise ValueError('Original landmark capture does not match')
    return {'path': path, 'generation': str(blob.generation),
            'recordingGeneration': generation, 'sha256': digest, 'version': json.loads(raw)['version']}

def landmarks_url(reference, recording, generation):
    if not reference:
        return None
    digest = reference.get('sha256', '')
    expected = recording.rsplit('/', 1)[0] + '/landmarks-' + str(generation) + '-' + digest + '.json'
    if (len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)
            or reference.get('path') != expected
            or reference.get('recordingGeneration') != str(generation)
            or not str(reference.get('generation', '')).isdigit()):
        raise ValueError('Original landmarks do not match this recording')
    blob = get_storage_bucket().blob(expected, generation=int(reference['generation']))
    return signed_url(blob, version='v4', method='GET',
                      expiration=timedelta(seconds=PLAYBACK_TTL_SECONDS),
                      query_parameters={'generation': reference['generation']})
