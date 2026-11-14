"""Real decoder checks against generated, non-personal videos."""
import shutil
import subprocess
import pytest
from scripts.inspect_hiring_video import inspect_video, compare_playback, VideoInspectionError
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


def test_playback_comparison_checks_timestamps_and_counts_without_modifying_original(video, tmp_path):
    duplicate = tmp_path / ('duplicate' + video.suffix)
    shutil.copyfile(video, duplicate)
    before = video.read_bytes()
    result = compare_playback(video, duplicate)
    assert result['technicalChecksPassed'] and result['maxFrameDriftMs'] == 0
    assert result['humanQualityAcceptanceRequired'] and not result['productionCompressionEnabled']
    assert result['retainedTogetherBytes'] == 2*len(before)
    changed = tmp_path/'changed.mp4'
    subprocess.run(['ffmpeg','-v','error','-i',str(video),'-r','5','-an','-c:v','mpeg4',
                    '-threads','1',str(changed)],capture_output=True,check=True,timeout=20)
    assert not compare_playback(video, changed)['technicalChecksPassed']
    assert video.read_bytes() == before


def test_comparing_a_recording_to_itself_is_rejected(video):
    with pytest.raises(VideoInspectionError, match='separate playback'):
        compare_playback(video, video)


def test_nonmonotonic_source_is_reported_and_blocks_compression_acceptance(video, tmp_path, monkeypatch):
    from scripts import inspect_hiring_video as inspector
    duplicate = tmp_path / ('comparison' + video.suffix)
    shutil.copyfile(video, duplicate)
    monkeypatch.setattr(inspector, '_frame_times', lambda path, ffprobe:
        [0.0, 0.2, 0.1] if path == video else [0.0, 0.1, 0.2])
    result = compare_playback(video, duplicate)
    assert result['sourceTimelineIssues'] == 1
    assert not result['technicalChecksPassed']
