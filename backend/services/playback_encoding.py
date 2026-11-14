"""Bounded, local-only playback encoding. Never imports the API or scores skills."""
import json
import math
import re
from pathlib import Path

from scripts.inspect_hiring_video import run, compare_playback, VideoInspectionError

# Version the byte-producing profile and gates together. No scaling, frame-rate
# conversion or B-frames: the published landmark timestamps must stay aligned.
PROFILE = 'h264-crf24-timing-v1'
INPUT = ['-max_alloc', '67108864', '-protocol_whitelist', 'file',
         '-format_whitelist', 'mov,matroska,webm', '-codec_whitelist', 'h264,vp8,vp9']


class EncodingSkipped(ValueError):
    """Expected unsupported input; original playback remains available."""


def encode_playback(source, target):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve() or target.exists():
        raise VideoInspectionError('A separate new output is required')
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
    run(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-threads', '1', *INPUT,
         '-copyts', '-start_at_zero', '-i', str(source), '-map', '0:v:0', '-an', '-sn', '-dn',
         '-t', '180', '-map_metadata', '-1', '-map_chapters', '-1', '-c:v', 'libx264',
         '-preset', 'fast', '-crf', '24', '-profile:v', 'high', '-bf', '0', '-threads', '2',
         '-pix_fmt', 'yuv420p', *colors, '-fps_mode', 'passthrough', '-enc_time_base', '-1',
         '-video_track_timescale', '60000', '-force_key_frames', 'expr:gte(t,n_forced*2)',
         '-movflags', '+faststart', '-fs', str(80 * 1024 * 1024), '-n', str(target)], 480)
    check = compare_playback(source, target)
    if not check['technicalChecksPassed']:
        raise EncodingSkipped('timing_or_metadata_gate')
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
