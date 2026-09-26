"""Offline media preflight; never updates an attempt or certifies a skill score.

Run in an isolated worker environment before using this with untrusted uploads.
The API does not invoke this tool. Only local MP4/MOV/WebM files are accepted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.hiring_capture import validate_capture

MAX_BYTES = 80 * 1024 * 1024
MAX_SECONDS = 180


class VideoInspectionError(ValueError):
    pass


def run(command, timeout):
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoInspectionError('Video inspector unavailable or time budget exceeded') from exc
    if result.returncode:
        # Decoder logs can contain local paths; do not return them as public errors.
        raise VideoInspectionError('Video container or decoding check failed')
    if len(result.stdout) > 1024 * 1024:
        raise VideoInspectionError('Video inspector output exceeded its limit')
    return result.stdout.decode('utf-8', errors='strict')


def inspect_video(path, capture=None, *, ffprobe='ffprobe', ffmpeg='ffmpeg'):
    path = Path(path)
    if not path.is_file() or path.suffix.lower() not in ('.mp4', '.mov', '.webm'):
        raise VideoInspectionError('A local MP4, MOV or WebM file is required')
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise VideoInspectionError('Video size exceeds the supported range')
    claim = validate_capture(capture)
    # Inspect a fixed private copy so the probe and decoder read identical bytes.
    with path.open('rb') as source:
        data = source.read(MAX_BYTES + 1)
    if not 0 < len(data) <= MAX_BYTES:
        raise VideoInspectionError('Video size changed or exceeds the supported range')
    digest = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory(prefix='hiring-video-') as directory:
        local = Path(directory) / ('recording' + path.suffix.lower())
        local.write_bytes(data)
        common = ['-protocol_whitelist', 'file', '-format_whitelist', 'mov,matroska,webm']
        raw = run([ffprobe, '-v', 'error', *common, '-show_entries',
                   'stream=codec_type,width,height:stream_side_data=rotation:format=duration',
                   '-of', 'json', str(local)], 15)
        try:
            info = json.loads(raw)
            streams = info['streams']
            videos = [item for item in streams if item.get('codec_type') == 'video']
            if len(videos) != 1 or any(item.get('codec_type') != 'video' for item in streams):
                raise ValueError('one video stream without audio required')
            stream = videos[0]
            width, height = stream['width'], stream['height']
            if (type(width) is not int or type(height) is not int or
                    not 1 <= width <= 4096 or not 1 <= height <= 4096 or width*height > 8388608):
                raise ValueError('geometry limit')
            rotations = [item.get('rotation', 0) for item in stream.get('side_data_list', [])]
            if any(rotation != 0 for rotation in rotations):
                raise ValueError('rotation needs explicit coordinate handling')
            duration = info.get('format', {}).get('duration')
            if duration is not None and (not math.isfinite(float(duration)) or not 0 < float(duration) <= MAX_SECONDS):
                raise ValueError('duration limit')
        except (KeyError, TypeError, ValueError) as exc:
            raise VideoInspectionError('Unsupported video stream, geometry, rotation or duration') from exc
        progress = run([ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-threads', '1',
                        *common, '-i', str(local), '-map', '0:v:0', '-an', '-sn', '-dn',
                        '-t', str(MAX_SECONDS + 1), '-threads', '1', '-progress', 'pipe:1',
                        '-nostats', '-f', 'null', '-'], 60)
        values = dict(line.split('=', 1) for line in progress.splitlines() if '=' in line)
        try:
            frames, elapsed = int(values['frame']), int(values['out_time_us']) / 1000000
            if frames < 2 or not 0 < elapsed < MAX_SECONDS or values.get('progress') != 'end':
                raise ValueError('incomplete or overlong recording')
        except (KeyError, ValueError) as exc:
            raise VideoInspectionError('Recording duration or decoded frames are insufficient') from exc
    issues = []
    if claim is None:
        issues.append('capture-metadata-missing')
    else:
        if (claim['sourceWidth'], claim['sourceHeight']) != (width, height):
            issues.append('capture-geometry-mismatch')
        issues.extend(claim['issues'])
        if not claim['samples']:
            issues.append('inference-samples-missing')
    return {'schema': 'hiring-video-preflight-v1', 'serverVerified': False,
            'sha256': digest, 'bytes': len(data), 'width': width, 'height': height,
            'decodedFrames': frames, 'decodedDurationSec': elapsed, 'issues': issues,
            'scope': 'Container decoding and geometry only; no motion or identity verification',
            'captureDurationDeltaMs': round(elapsed*1000-claim['durationMs']) if claim else None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    claim = json.loads(args.capture.read_text()) if args.capture else None
    args.output.write_text(json.dumps(inspect_video(args.video, claim), indent=2))
    print('Local video preflight saved; serverVerified=false. No cloud or applicant changes.')
