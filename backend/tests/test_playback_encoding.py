"""Actual encoder gates using synthetic files, never applicant recordings."""
import shutil
import subprocess
import pytest
from services.playback_encoding import encode_playback, EncodingSkipped
from scripts.inspect_hiring_video import VideoInspectionError, inspect_video

pytestmark = pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='decoder tools required')


def make_video(path, *, size='320x240', audio=False):
    args = ['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'testsrc2=s={size}:r=24']
    if audio:
        args += ['-f', 'lavfi', '-i', 'anullsrc']
    subprocess.run([*args, '-t', '0.25' if size != '320x240' else '2', '-c:v', 'libx264',
        '-preset', 'ultrafast', '-crf', '4', '-threads', '1',
        *(['-c:a', 'aac'] if audio else ['-an']), str(path)], check=True, capture_output=True, timeout=30)


def test_actual_encode_keeps_original_timestamps_geometry_and_quality(tmp_path):
    source, target = tmp_path/'source.mp4', tmp_path/'playback.mp4'
    make_video(source)
    before = source.read_bytes()
    result = encode_playback(source, target)
    assert source.read_bytes() == before
    assert result['reductionPercent'] >= 10 and result['maxFrameDriftMs'] <= 2
    assert result['meanSsim'] >= .985 and result['minimumSsim'] >= .95
    assert inspect_video(target)['decodedFrames'] == 48


@pytest.mark.parametrize('size,audio', [('1920x1080', False), ('320x240', True)])
def test_oversized_capture_and_audio_fall_back_before_encoding(tmp_path, size, audio):
    source, target = tmp_path/'source.mp4', tmp_path/'playback.mp4'
    make_video(source, size=size, audio=audio)
    with pytest.raises((EncodingSkipped, VideoInspectionError)):
        encode_playback(source, target)
    assert not target.exists() and source.exists()


def test_existing_output_cannot_overwrite_evidence(tmp_path):
    source, target = tmp_path/'source.mp4', tmp_path/'playback.mp4'
    source.write_bytes(b'original'); target.write_bytes(b'previous')
    with pytest.raises(VideoInspectionError): encode_playback(source, source)
    with pytest.raises(VideoInspectionError): encode_playback(source, target)
    assert source.read_bytes() == b'original' and target.read_bytes() == b'previous'
