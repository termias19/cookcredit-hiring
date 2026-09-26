from types import SimpleNamespace
from urllib.parse import quote
import pytest
from services import assessment_media as media


def url(path='skill_videos/alice/clip.webm', bucket=None):
    return f'https://firebasestorage.googleapis.com/v0/b/{bucket or media.STORAGE_BUCKET}/o/{quote(path, safe="")}?alt=media&token=ignored'


@pytest.mark.parametrize('bad', [
    'http://127.0.0.1/private', 'https://169.254.169.254/metadata',
    'https://evil.example/?path=skill_videos%2Falice%2Fclip.webm',
    url('skill_videos/bob/clip.webm'), url('skill_videos/alice/../bob/clip.webm'),
    url('skill_videos/alice/clip.webm', 'foreign-bucket'),
    url().replace('googleapis.com', 'googleapis.com.evil.test'),
    url().replace('https://', 'https://alice@'),
])
def test_foreign_or_forged_locator_is_rejected(bad):
    with pytest.raises(media.InvalidRecording):
        media.owned_recording_path(bad, 'alice')


def test_download_pins_generation_and_does_not_use_download_token(monkeypatch):
    observed = []
    blob = SimpleNamespace(content_type='video/webm', size=5, reload=lambda **kw: None,
                           download_as_bytes=lambda **kw: observed.append(kw) or b'video')
    def object_ref(path, generation):
        observed.append((path, generation))
        return blob
    monkeypatch.setattr(media, 'get_storage_bucket', lambda: SimpleNamespace(blob=object_ref))
    assert media.read_recording(url(), 'alice', '123') == (b'video', 'video/webm')
    assert observed[0] == ('skill_videos/alice/clip.webm', 123)
    assert observed[1]['if_generation_match'] == 123


def test_oversized_object_is_not_downloaded(monkeypatch):
    blob = SimpleNamespace(content_type='video/webm', size=media.MAX_VIDEO_BYTES+1, reload=lambda **kw: None)
    monkeypatch.setattr(media, 'get_storage_bucket', lambda: SimpleNamespace(blob=lambda *a, **kw: blob))
    with pytest.raises(media.InvalidRecording):
        media.read_recording(url(), 'alice', '123')


def test_live_engine_recording_namespace_is_owner_and_assessment_scoped():
    path = 'cookcredit-skill/users/alice/assessments/assessment_1/recording.webm'
    assert media.owned_recording_path(url(path), 'alice') == path
    for bad in (
        'cookcredit-skill/users/bob/assessments/assessment_1/recording.webm',
        'cookcredit-skill/users/alice/assessments/../recording.webm',
        'cookcredit-skill/users/alice/assessments/assessment_1/other.webm',
        'cookcredit-skill/users/alice/assessment_1/recording.webm',
    ):
        with pytest.raises(media.InvalidRecording):
            media.owned_recording_path(url(bad), 'alice')
