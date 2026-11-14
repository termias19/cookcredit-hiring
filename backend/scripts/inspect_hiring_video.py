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
                   'stream=codec_type,width,height,sample_aspect_ratio,color_range,color_space,color_transfer,color_primaries:stream_side_data=rotation:format=duration',
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
                        '-t', str(MAX_SECONDS + 1), '-threads', '1',
                        # A null-output diagnostic must not resample VFR media
                        # to ffprobe's guessed nominal frame rate.
                        '-fps_mode', 'passthrough', '-enc_time_base', '-1', '-progress', 'pipe:1',
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
            'sampleAspectRatio': stream.get('sample_aspect_ratio'),
            'colorMetadata': {key: stream.get(key) for key in (
                'color_range', 'color_space', 'color_transfer', 'color_primaries')},
            'decodedFrames': frames, 'decodedDurationSec': elapsed, 'issues': issues,
            'containerDurationSec': float(duration) if duration is not None else None,
            'scope': 'Container decoding and geometry only; no motion or identity verification',
            'captureDurationDeltaMs': round(elapsed*1000-claim['durationMs']) if claim else None}


def _frame_times(path, ffprobe):
    raw = run([ffprobe, '-v', 'error', '-protocol_whitelist', 'file',
               '-format_whitelist', 'mov,matroska,webm', '-select_streams', 'v:0',
               '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time',
               '-of', 'csv=p=0', str(path)], 60)
    try:
        times = [float(line.split(',', 1)[0]) for line in raw.splitlines() if line.strip()]
        if not 2 <= len(times) <= 21600 or not all(math.isfinite(t) and t >= 0 for t in times):
            raise ValueError('invalid frame timeline')
        return times
    except ValueError:
        raise VideoInspectionError('Frame timestamps are missing, invalid or exceed the limit') from None


def compare_playback(original, playback, *, ffprobe='ffprobe', ffmpeg='ffmpeg'):
    """Offline gate for a proposed derivative; never replaces or uploads evidence.

    Identical frame counts alone cannot protect time-aligned landmark overlays.
    Two milliseconds is a technical diagnostic tolerance, not a quality score.
    """
    original, playback = Path(original), Path(playback)
    if original.resolve() == playback.resolve():
        raise VideoInspectionError('Compare a separate playback copy')
    source = inspect_video(original, ffprobe=ffprobe, ffmpeg=ffmpeg)
    copy = inspect_video(playback, ffprobe=ffprobe, ffmpeg=ffmpeg)
    before, after = _frame_times(original, ffprobe), _frame_times(playback, ffprobe)
    matching_count = len(before) == len(after)
    source_timeline_issues = sum(b <= a for a, b in zip(before, before[1:]))
    playback_timeline_issues = sum(b <= a for a, b in zip(after, after[1:]))
    drift = max(abs(a-b)*1000 for a, b in zip(before, after)) if matching_count else None
    geometry = (source['width'], source['height']) == (copy['width'], copy['height'])
    aspect = source['sampleAspectRatio'] == copy['sampleAspectRatio']
    color = source['colorMetadata'] == copy['colorMetadata']
    duration_delta = abs(source['decodedDurationSec']-copy['decodedDurationSec'])*1000
    source_container, copy_container = source.get('containerDurationSec'), copy.get('containerDurationSec')
    container_delta = abs(source_container-copy_container)*1000 if source_container is not None and copy_container is not None else None
    # Reject a source changed between the decoding and timeline passes. Hash in
    # chunks so the comparison does not retain another full recording in RAM.
    for path, expected in ((original, source['sha256']), (playback, copy['sha256'])):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024*1024), b''): digest.update(chunk)
        if digest.hexdigest() != expected:
            raise VideoInspectionError('A local recording changed during comparison')
    return {'schema': 'hiring-playback-comparison-v1', 'localOnly': True,
            'sourceSha256': source['sha256'], 'playbackSha256': copy['sha256'],
            'sourceBytes': source['bytes'], 'playbackBytes': copy['bytes'],
            'retainedTogetherBytes': source['bytes'] + copy['bytes'],
            'reductionPercent': round(100*(1-copy['bytes']/source['bytes']), 2),
            'sameGeometry': geometry, 'sourceFrames': len(before), 'playbackFrames': len(after),
            'sameSampleAspectRatio': aspect, 'sameDeclaredColorMetadata': color,
            'sourceColorMetadata': source['colorMetadata'], 'playbackColorMetadata': copy['colorMetadata'],
            'decodedDurationDeltaMs': round(duration_delta, 4),
            'containerDurationDeltaMs': round(container_delta, 4) if container_delta is not None else None,
            'sourceTimelineIssues': source_timeline_issues, 'playbackTimelineIssues': playback_timeline_issues,
            'maxFrameDriftMs': round(drift, 4) if drift is not None else None,
            'technicalChecksPassed': bool(geometry and aspect and color and duration_delta <= 2
                                         and (container_delta is None or container_delta <= 2)
                                         and matching_count and drift <= 2
                                         and not source_timeline_issues and not playback_timeline_issues),
            'humanQualityAcceptanceRequired': True, 'productionCompressionEnabled': False,
            'scope': 'Decoding, geometry/aspect, declared color, duration and timestamps only; no skill, identity or visual-quality certification'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--playback', type=Path, help='Optional local proposed compressed copy; no cloud writes')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {p.resolve() for p in (args.video, args.playback, args.capture) if p}:
        parser.error('Output must be separate from every input file')
    claim = json.loads(args.capture.read_text()) if args.capture else None
    result = (compare_playback(args.video, args.playback) if args.playback
              else inspect_video(args.video, claim))
    args.output.write_text(json.dumps(result, indent=2))
    print('Local video preflight saved; serverVerified=false. No cloud or applicant changes.')
