import gzip
import hashlib
import json
import struct
import pytest
from services.hiring_exact_frames import read_exact_frames

MODEL='a'*64
RUNTIME='b'*64

def archive(*, pixels=b'\x07'*2560, mutate=lambda h:h, extra=b'', compressed=None):
    chunk=gzip.compress(pixels) if compressed is None else compressed
    header=dict(version=1,encoding='rgba8-gzip-per-frame',trust='client-claim',
        width=320,height=2,sourceWidth=640,sourceHeight=4,modelSha256=MODEL,runtimeSha256=RUNTIME,
        frames=[dict(timestampMs=1000.123456789,sessionTimeSec=.123456789,hand='Right',
            sha256=hashlib.sha256(pixels).hexdigest(),compressedBytes=len(chunk))])
    mutate(header)
    encoded=json.dumps(header).encode()
    return b'CCEF0001'+struct.pack('>I',len(encoded))+encoded+chunk+extra

def decode(data):
    h,frames=read_exact_frames(data,model_sha256=MODEL,runtime_sha256=RUNTIME)
    return h,list(frames)

def test_lossless_clocks_and_pixels_without_authority():
    h,frames=decode(archive())
    assert h['trust']=='client-claim' and 'serverVerified' not in h
    assert frames[0][0]['timestampMs']==1000.123456789
    assert frames[0][0]['sessionTimeSec']==.123456789
    assert frames[0][1]==b'\x07'*2560

@pytest.mark.parametrize('damage',[
    lambda h:h.update(serverVerified=True),lambda h:h.update(version=True),
    lambda h:h.update(modelSha256='c'*64),lambda h:h.update(runtimeSha256='c'*64),
    lambda h:h.update(width=480),lambda h:h.update(height=3),lambda h:h.update(frames=[]),
    lambda h:h['frames'][0].update(timestampMs=float('nan')),
    lambda h:h['frames'][0].update(sessionTimeSec=-1),
    lambda h:h['frames'][0].update(compressedBytes=True),
    lambda h:h['frames'][0].update(sha256='0'*64),
    lambda h:h['frames'].append(dict(h['frames'][0])),
])
def test_rejects_malformed_or_forged_archive(damage):
    with pytest.raises(ValueError):decode(archive(mutate=damage))

@pytest.mark.parametrize('data',[
    archive(extra=b'x'),archive()[:-1],archive(pixels=b'x'*2561),
    archive(compressed=gzip.compress(b'x'*(1024*1024))),
    archive(compressed=gzip.compress(b'\x07'*2560)+gzip.compress(b'extra')),
    archive(compressed=b'not gzip'),b'WRONG000'+archive()[8:],
])
def test_rejects_truncation_trailing_data_and_decompression_bombs(data):
    with pytest.raises(ValueError):decode(data)

def test_duplicate_json_keys_rejected():
    data=archive();n=struct.unpack('>I',data[8:12])[0]
    header=b'{"version":1,'+data[13:12+n]
    bad=data[:8]+struct.pack('>I',len(header))+header+data[12+n:]
    with pytest.raises(ValueError,match='Duplicate'):decode(bad)


def version_two(h):
    h.update(version=2,context={'initialHand':'Right','countdownSec':3,'modelState':'fresh'},events=[])

def test_v2_preserves_multiple_trailing_controls():
    def controls(h):
        version_two(h)
        h['events']=[{'type':'hand-change','hand':'Left','beforeFrame':1},
                     {'type':'hand-change','hand':'Right','beforeFrame':1},
                     {'type':'session-reset','hand':'Right','beforeFrame':1}]
    h,frames=decode(archive(mutate=controls))
    assert len(h['events'])==3 and len(frames)==1

@pytest.mark.parametrize('event',[
    {'type':'hand-change','hand':'Right','beforeFrame':0},
    {'type':'session-reset','hand':'Left','beforeFrame':0},
    {'type':'hand-change','hand':'Left','beforeFrame':0},
    {'type':'hand-change','hand':'Left','beforeFrame':2},
    {'type':'session-reset','hand':'Right','beforeFrame':True},
])
def test_v2_rejects_contradictory_or_out_of_range_controls(event):
    def damage(h):
        version_two(h);h['events']=[event]
    with pytest.raises(ValueError):decode(archive(mutate=damage))
