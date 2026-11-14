"""Bounded, local-only playback encoding. Never imports the API or scores skills."""
import json
import math
import re
import hashlib
from pathlib import Path
from fractions import Fraction

from scripts.inspect_hiring_video import run, compare_playback, VideoInspectionError, _frame_times

# Version the byte-producing profile and gates together. No scaling, frame-rate
# conversion or B-frames: the published landmark timestamps must stay aligned.
PROFILE = 'h264-crf24-timing-v3'
INPUT = ['-max_alloc', '67108864', '-protocol_whitelist', 'file',
         '-format_whitelist', 'mov,matroska,webm', '-codec_whitelist', 'h264,vp8,vp9']


class EncodingSkipped(ValueError):
    """Expected unsupported input; original playback remains available."""
    def __init__(self, code, *, checks=None):
        super().__init__(code)
        self.checks = checks or {}


def _final_frame_duration(source, duration):
    """Preserve the real final sample length, not an encoder's nominal FPS.

    FFmpeg 7 can keep every VFR PTS yet extend the last MP4 sample. Read the
    pinned source's decoded presentation timeline and declared end time. Raw
    packet duration fields are optional and differ between FFmpeg versions.
    Subsequent decoding/count/timestamp/container checks remain mandatory.
    """
    times = _frame_times(source, 'ffprobe')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise EncodingSkipped('unsupported_timing', checks={'timingReason':'nonmonotonic_frame_timeline'})
    final = Fraction(str(duration)) - Fraction(str(times[-1]))
    if not 0 < final <= 1:
        raise EncodingSkipped('unsupported_timing', checks={'timingReason':'final_visible_interval_outside_limits'})
    # The bitstream filter sees encoder packet time units (TB), which can
    # differ from the MP4 track time base. All interpolated values are integers.
    expression = (f'setts=pts=PTS:dts=DTS:duration=if(eq(N\\,{len(times)-1})\\,'
                  f'floor({final.numerator}/({final.denominator}*TB)+0.5)\\,DURATION)')
    return len(times), expression


def encode_playback(source, target):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve() or target.exists():
        raise VideoInspectionError('A separate new output is required')
    digest = hashlib.sha256()
    with source.open('rb') as handle:
        for chunk in iter(lambda: handle.read(256 * 1024), b''): digest.update(chunk)
    original_sha = digest.hexdigest()
    info = json.loads(run(['ffprobe', '-v', 'error', *INPUT, '-show_streams',
                           '-show_format', '-of', 'json', str(source)], 15))
    streams = info.get('streams', [])
    stream = streams[0] if len(streams) == 1 else {}
    try:
        width, height = int(stream['width']), int(stream['height'])
        duration = float(info['format']['duration'])
        if (stream['codec_type'] != 'video' or stream['codec_name'] not in ('h264', 'vp8', 'vp9')
                or not math.isfinite(duration) or not 0 < duration < 180
                or min(width, height) < 2 or max(width, height) > 1280
                or width * height > 921600 or width % 2 or height % 2
                or any(s.get('rotation', 0) != 0 for s in stream.get('side_data_list', []))):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise EncodingSkipped('unsupported_capture') from None
    colors = []
    for key, option in (('color_range', '-color_range'), ('color_space', '-colorspace'),
                        ('color_transfer', '-color_trc'), ('color_primaries', '-color_primaries')):
        value = stream.get(key)
        if value and value != 'unknown':
            if not re.fullmatch(r'[a-z0-9_-]{1,24}', value):
                raise EncodingSkipped('unsupported_color')
            colors.extend([option, value])
    frame_count, duration_filter = _final_frame_duration(source, duration)
    run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', *INPUT,
         '-copyts', '-start_at_zero', '-i', str(source), '-map', '0:v:0', '-an', '-sn', '-dn',
         '-t', '180', '-map_metadata', '-1', '-map_chapters', '-1', '-c:v', 'libx264',
         '-preset', 'fast', '-crf', '24', '-profile:v', 'high', '-bf', '0', '-threads', '2',
         '-pix_fmt', 'yuv420p', *colors, '-fps_mode', 'passthrough', '-enc_time_base', '-1',
         '-video_track_timescale', '60000', '-force_key_frames', 'expr:gte(t,n_forced*2)',
         '-bsf:v', duration_filter,
         '-movflags', '+faststart', '-fs', str(80 * 1024 * 1024), '-n', str(target)], 480)
    check = compare_playback(source, target)
    if check['sourceSha256'] != original_sha:
        raise VideoInspectionError('The local source changed during encoding')
    if not check['technicalChecksPassed'] or check['sourceFrames'] != frame_count:
        details = {key: check[key] for key in ('sameGeometry', 'sameSampleAspectRatio',
            'sameDeclaredColorMetadata', 'sourceFrames', 'playbackFrames', 'sourceTimelineIssues',
            'playbackTimelineIssues', 'maxFrameDriftMs', 'decodedDurationDeltaMs', 'containerDurationDeltaMs')}
        raise EncodingSkipped('timing_or_metadata_gate', checks=details)
    if check['reductionPercent'] < 10:
        raise EncodingSkipped('insufficient_savings')
    # SSIM is an additional conservative gate, never a skill/identity verdict.
    quality = run(['ffmpeg', '-nostdin', '-v', 'info', '-threads', '1', *INPUT,
                   '-i', str(source), '-threads', '1', *INPUT, '-i', str(target),
                   '-filter_complex_threads', '1', '-lavfi',
                   '[0:v]settb=AVTB,setpts=PTS-STARTPTS[a];'
                   '[1:v]settb=AVTB,setpts=PTS-STARTPTS[b];'
                   '[a][b]ssim,metadata=mode=print:key=lavfi.ssim.All:file=-',
                   '-an', '-f', 'null', '-'], 90)
    scores = [float(value) for value in re.findall(r'lavfi.ssim.All=([0-9.]+)', quality)]
    if (len(scores) != check['sourceFrames'] or not all(math.isfinite(s) for s in scores)
            or min(scores, default=0) < .95 or sum(scores) / len(scores) < .985):
        raise EncodingSkipped('quality_gate')
    return {**{key: check[key] for key in ('sourceSha256', 'playbackSha256', 'sourceBytes',
            'playbackBytes', 'reductionPercent', 'maxFrameDriftMs')},
            'meanSsim': round(sum(scores) / len(scores), 6), 'minimumSsim': round(min(scores), 6)}
