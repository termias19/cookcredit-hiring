"""Bounded lossless input archive reader, not a verifier or upload endpoint.

Client hashes prove integrity only. Ownership, model state, control events and
agreement still need separate verification. No client flag authorizes a score.
"""
import hashlib
import json
import math
import struct
import zlib

MAX_COMPRESSED = 80 * 1024 * 1024
MAX_HEADER = 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate exact-frame metadata key')
        result[key] = value
    return result


def read_exact_frames(blob, *, model_sha256, runtime_sha256):
    """Validate metadata eagerly, then yield bounded independently hashed pixels.

    Callers must exhaust the iterator before accepting any evidence; a later
    corrupt frame invalidates the complete archive, never just that frame.
    """
    def require(condition):
        if not condition:
            raise ValueError('Invalid exact-frame evidence')
    def integer(n, low, high):
        return type(n) is int and low <= n <= high
    def number(n, low, high):
        return type(n) in (int, float) and math.isfinite(n) and low <= n <= high
    require(type(blob) is bytes and 12 < len(blob) <= MAX_COMPRESSED + MAX_HEADER + 12)
    require(blob[:8] == b'CCEF0001')
    size = struct.unpack('>I', blob[8:12])[0]
    require(0 < size <= MAX_HEADER and 12 + size < len(blob))
    try:
        header = json.loads(blob[12:12+size], object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Invalid exact-frame metadata') from exc
    require(type(header) is dict)
    require(type(header.get('version')) is int and header['version'] in (1, 2))
    fields = {
        'version', 'encoding', 'trust', 'width', 'height', 'sourceWidth',
        'sourceHeight', 'modelSha256', 'runtimeSha256', 'frames'}
    require(set(header) == (fields | {'context', 'events'} if header['version'] == 2 else fields))
    require(header['encoding'] == 'rgba8-gzip-per-frame' and header['trust'] == 'client-claim')
    require(type(header['width']) is int and header['width'] == 320)
    require(integer(header['height'], 1, 1280))
    require(all(integer(header[k], 1, 8192) for k in ('sourceWidth', 'sourceHeight')))
    require(header['height'] == max(1, math.floor(320*header['sourceHeight']/header['sourceWidth']+.5)))
    require(header['modelSha256'] == model_sha256 and header['runtimeSha256'] == runtime_sha256)
    require(all(isinstance(h, str) and len(h) == 64 and all(c in '0123456789abcdef' for c in h)
                for h in (model_sha256, runtime_sha256)))
    rows = header['frames']
    require(type(rows) is list and 1 <= len(rows) <= 6000)
    if header['version'] == 2:
        context, events = header['context'], header['events']
        require(type(context) is dict and set(context) == {'initialHand', 'countdownSec', 'modelState'})
        require(context['initialHand'] in ('Left', 'Right') and context['modelState'] == 'fresh')
        require(integer(context['countdownSec'], 0, 30))
        require(type(events) is list and len(events) <= 128)
        before = 0
        selected = context['initialHand']
        cursor = 0
        for event in events:
            require(type(event) is dict and set(event) == {'type', 'hand', 'beforeFrame'})
            require(integer(event['beforeFrame'], before, len(rows)))
            require(event['type'] in ('hand-change', 'session-reset') and event['hand'] in ('Left', 'Right'))
            for row in rows[cursor:event['beforeFrame']]:
                require(type(row) is dict and row.get('hand') == selected)
            cursor = before = event['beforeFrame']
            require((event['hand'] != selected) if event['type'] == 'hand-change' else (event['hand'] == selected))
            selected = event['hand']
        for row in rows[cursor:]:
            require(type(row) is dict and row.get('hand') == selected)
    previous = -1
    position = 12 + size
    starts = []
    for row in rows:
        require(type(row) is dict and set(row) == {'timestampMs', 'sessionTimeSec', 'hand', 'sha256', 'compressedBytes'})
        require(number(row['timestampMs'], 0, 2**53-1) and row['timestampMs'] > previous)
        require(number(row['sessionTimeSec'], 0, 180) and row['hand'] in ('Left', 'Right'))
        require(integer(row['compressedBytes'], 1, MAX_COMPRESSED))
        require(isinstance(row['sha256'], str) and len(row['sha256']) == 64 and
                all(c in '0123456789abcdef' for c in row['sha256']))
        starts.append(position)
        position += row['compressedBytes']
        require(position <= len(blob))
        previous = row['timestampMs']
    require(position == len(blob) and len(blob)-12-size <= MAX_COMPRESSED)
    require(rows[-1]['timestampMs']-rows[0]['timestampMs'] <= 180000)
    expected = header['width'] * header['height'] * 4
    require(expected * len(rows) <= 512 * 1024 * 1024)

    def frames():
        for row, start in zip(rows, starts):
            inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
            try:
                pixels = inflater.decompress(blob[start:start+row['compressedBytes']], expected+1)
            except zlib.error as exc:
                raise ValueError('Invalid exact-frame compression') from exc
            require(len(pixels) == expected and inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail)
            require(hashlib.sha256(pixels).hexdigest() == row['sha256'])
            yield dict(row), pixels
    return header, frames()
