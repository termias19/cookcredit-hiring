"""Compression metadata gates run in CI even without the optional local decoder."""
import hashlib
import pytest
from scripts import inspect_hiring_video as inspector


@pytest.fixture
def comparison(tmp_path, monkeypatch):
    original, playback = tmp_path/'original.mp4', tmp_path/'copy.mp4'
    original.write_bytes(b'controlled-original'); playback.write_bytes(b'controlled-copy')
    source = dict(width=720, height=1280, sampleAspectRatio='1:1',
        colorMetadata=dict(color_range='pc', color_space='bt470bg',
                           color_transfer='smpte170m', color_primaries='bt470bg'),
        decodedDurationSec=63.063, bytes=original.stat().st_size,
        sha256=hashlib.sha256(original.read_bytes()).hexdigest())
    copy = {**source, 'bytes':playback.stat().st_size,
            'colorMetadata':dict(source['colorMetadata']),
            'sha256':hashlib.sha256(playback.read_bytes()).hexdigest()}
    monkeypatch.setattr(inspector, 'inspect_video', lambda path, **options: source if path==original else copy)
    monkeypatch.setattr(inspector, '_frame_times', lambda *args: [0.0, 0.033, 0.067])
    return original, playback, source, copy


def test_equivalent_metadata_and_timing_pass_without_certifying_quality(comparison):
    original, playback, _, _ = comparison
    result = inspector.compare_playback(original, playback)
    assert result['technicalChecksPassed']
    assert result['sameDeclaredColorMetadata'] and result['sameSampleAspectRatio']
    assert result['humanQualityAcceptanceRequired']
    assert not result['productionCompressionEnabled']


@pytest.mark.parametrize('field,value', [
    ('color_range','tv'), ('color_space','bt709'),
    ('color_transfer','bt709'), ('color_primaries','bt709'),
])
def test_changed_color_metadata_is_not_accepted_as_unchanged_evidence(comparison, field, value):
    original, playback, _, copy = comparison
    copy['colorMetadata'][field]=value
    result=inspector.compare_playback(original, playback)
    assert not result['sameDeclaredColorMetadata'] and not result['technicalChecksPassed']


@pytest.mark.parametrize('field,value', [('sampleAspectRatio','4:3'), ('decodedDurationSec',63.103)])
def test_aspect_and_duration_changes_fail_even_when_frame_count_matches(comparison, field, value):
    original, playback, _, copy = comparison
    copy[field]=value
    result=inspector.compare_playback(original, playback)
    assert result['sourceFrames']==result['playbackFrames'] and result['sameGeometry']
    assert not result['technicalChecksPassed']


def test_container_duration_mismatch_is_not_hidden_by_equal_decoded_counters(comparison):
    original, playback, source, copy = comparison
    source['containerDurationSec']=63.063;copy['containerDurationSec']=64.063
    result=inspector.compare_playback(original, playback)
    assert result['decodedDurationDeltaMs']==0 and result['containerDurationDeltaMs']==1000
    assert not result['technicalChecksPassed']


def test_null_mux_progress_beyond_mp4_end_is_not_a_presentation_change(comparison):
    original, playback, source, copy = comparison
    source['containerDurationSec']=copy['containerDurationSec']=63.063
    source['decodedDurationSec']=63.0883
    result=inspector.compare_playback(original, playback)
    assert result['decodedDurationDeltaMs']==25.3
    assert result['presentationDurationDeltaMs']==0
    assert result['technicalChecksPassed']


def test_incomplete_decoder_interval_is_not_hidden_by_equal_containers(comparison):
    original, playback, source, copy = comparison
    source['containerDurationSec']=copy['containerDurationSec']=63.063
    copy['decodedDurationSec']=63.0
    result=inspector.compare_playback(original, playback)
    assert result['presentationDurationDeltaMs']==63
    assert not result['technicalChecksPassed']


def test_container_end_cannot_hide_decoded_frames_after_the_visible_interval(comparison):
    original, playback, source, copy = comparison
    source['containerDurationSec']=copy['containerDurationSec']=.05
    result=inspector.compare_playback(original, playback)
    assert not result['presentationEndCoversDecodedFrames']
    assert not result['technicalChecksPassed']
