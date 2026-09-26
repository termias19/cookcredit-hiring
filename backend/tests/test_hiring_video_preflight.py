"""Real decoder checks against generated, non-personal videos."""
import shutil
import subprocess
import pytest
from scripts.inspect_hiring_video import inspect_video, VideoInspectionError
from tests.test_hiring_capture import claim

pytestmark = pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),
                               reason='offline decoder tools required')


@pytest.fixture(params=['mp4', 'webm'])
def video(tmp_path, request):
    path = tmp_path / ('clip.' + request.param)
    codec = 'mpeg4' if request.param == 'mp4' else 'libvpx'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:r=10',
                    '-t', '1', '-an', '-c:v', codec, '-threads', '1', str(path)], check=True,
                   capture_output=True, timeout=20)
    return path


def test_real_decoding_and_geometry_mismatch_remain_unverified(video):
    capture = claim()
    capture['durationMs'] = 1000
    result = inspect_video(video, capture)
    assert result['decodedFrames'] == 10
    assert result['width'] == 320 and result['height'] == 240
    assert result['serverVerified'] is False
    assert 'capture-geometry-mismatch' in result['issues']
    capture.update(sourceWidth=320, sourceHeight=240)
    matching = inspect_video(video, capture)
    assert matching['issues'] == []
    assert matching['serverVerified'] is False
    assert matching['sha256'] == result['sha256']


def test_missing_capture_stays_flagged(video):
    assert inspect_video(video)['issues'] == ['capture-metadata-missing']


def test_corrupt_container_and_remote_paths_are_rejected(tmp_path):
    bad = tmp_path/'bad.mp4'
    bad.write_bytes(b'not a recording')
    with pytest.raises(VideoInspectionError): inspect_video(bad)
    with pytest.raises(VideoInspectionError): inspect_video('https://example.test/clip.mp4')


def test_timeout_fails_closed(video, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('ffprobe', 15)
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(VideoInspectionError, match='time budget'):
        inspect_video(video)


def test_audio_is_rejected_instead_of_retained_silently(tmp_path):
    path = tmp_path/'audio.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=32x32:r=10',
                    '-f', 'lavfi', '-i', 'anullsrc', '-t', '1', '-c:v', 'mpeg4',
                    '-c:a', 'aac', '-threads', '1', str(path)], check=True,
                   capture_output=True, timeout=20)
    with pytest.raises(VideoInspectionError, match='Unsupported video stream'):
        inspect_video(path)


def test_webm_without_duration_header_is_measured_by_decoding(tmp_path):
    path = tmp_path/'live.webm'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=32x32:r=10',
                    '-t', '1', '-an', '-c:v', 'libvpx', '-threads', '1', '-live', '1', str(path)],
                   check=True, capture_output=True, timeout=20)
    result = inspect_video(path)
    assert result['decodedFrames'] == 10
    assert 0 < result['decodedDurationSec'] <= 1
    assert result['serverVerified'] is False
