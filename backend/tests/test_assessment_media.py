from types import SimpleNamespace
from urllib.parse import quote
import pytest
from services import assessment_media as media
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from google.api_core.exceptions import NotFound, Forbidden, DeadlineExceeded


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


@pytest.fixture
def playback(monkeypatch):
    blob = SimpleNamespace(content_type='video/mp4', size=1024, generation=123,
                           time_created=datetime.now(timezone.utc) - timedelta(days=1), reload=Mock())
    bucket = SimpleNamespace(blob=Mock(return_value=blob))
    signer = Mock(return_value='https://example.test/signed')
    monkeypatch.setattr(media, 'get_storage_bucket', lambda: bucket)
    monkeypatch.setattr(media, 'signed_url', signer)
    return blob, bucket, signer


def test_playback_checks_exact_generation_before_signing(playback):
    blob, bucket, signer = playback
    observation = {}
    assert media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice', observation=observation)
    bucket.blob.assert_called_once_with('skill_videos/alice/clip.mp4', generation=123)
    blob.reload.assert_called_once_with(timeout=10, retry=None)
    assert observation['createdAt'] == blob.time_created.isoformat()
    assert observation['expiresAt'] == (blob.time_created + timedelta(days=30)).isoformat()
    assert media.recording_view({'recording_availability':observation}, '123')['state'] == 'ready'
    assert signer.call_args.kwargs['query_parameters'] == {'generation':'123'}


def test_absent_object_cannot_receive_a_signed_url_or_invent_expiry(playback):
    blob, _, signer = playback
    blob.reload.side_effect = NotFound('private object path and identifier')
    observation = {}
    with pytest.raises(media.RecordingUnavailable, match='unavailable') as failure:
        media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice', observation=observation)
    assert failure.value.code == 'recording_missing'
    assert observation['state'] == 'unavailable' and 'expiresAt' not in observation
    assert 'private' not in str(failure.value)
    signer.assert_not_called()


def test_existing_expired_object_cannot_bypass_retention(playback):
    blob, _, signer = playback
    blob.time_created = datetime.now(timezone.utc) - timedelta(days=31)
    observation = {}
    with pytest.raises(media.RecordingUnavailable) as failure:
        media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice', observation=observation)
    assert failure.value.code == 'recording_expired'
    assert observation['state'] == 'expired'
    signer.assert_not_called()


def test_signed_link_cannot_outlive_retention_boundary(playback):
    blob, _, signer = playback
    blob.time_created = datetime.now(timezone.utc) - timedelta(days=30) + timedelta(seconds=40)
    media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice')
    assert signer.call_args.kwargs['expiration'] == blob.time_created + timedelta(days=30)


def test_saved_expiry_survives_missing_object_and_retry(playback):
    blob, _, signer = playback
    snapshot = media.recording_snapshot(blob)
    now = datetime.now(timezone.utc)
    assert media.recording_view({'recording_availability':snapshot}, '123', now=blob.time_created+timedelta(days=30))['state'] == 'expired'
    snapshot['expiresAt'] = (now-timedelta(seconds=1)).isoformat()
    with pytest.raises(media.RecordingUnavailable):
        media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice', observation=snapshot)
    blob.reload.assert_not_called()
    signer.assert_not_called()


@pytest.mark.parametrize('error,code', [(Forbidden('private'), 'storage_permission_denied'),
                                      (DeadlineExceeded('private'), 'storage_timeout')])
def test_provider_errors_have_safe_categories_and_never_sign(playback, error, code):
    blob, _, signer = playback
    blob.reload.side_effect = error
    with pytest.raises(media.RecordingPlaybackError) as failure:
        media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice')
    assert failure.value.code == code and 'private' not in str(failure.value)
    signer.assert_not_called()


def test_signing_failure_is_distinct_from_storage_failure(playback):
    _, _, signer = playback
    signer.side_effect = RuntimeError('private credential context')
    with pytest.raises(media.RecordingPlaybackError) as failure:
        media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice')
    assert failure.value.code == 'signing_failed' and 'private' not in str(failure.value)


@pytest.mark.parametrize('values', [{'generation':124}, {'size':0}, {'size':media.MAX_VIDEO_BYTES+1}, {'content_type':'text/html'}])
def test_invalid_pinned_media_is_not_signed(playback, values):
    blob, _, signer = playback
    for key, value in values.items(): setattr(blob,key,value)
    with pytest.raises(media.InvalidRecording):
        media.playback_url('skill_videos/alice/clip.mp4', '123', 'alice')
    signer.assert_not_called()


def test_availability_is_bound_to_generation_and_old_records_stay_unchecked():
    snapshot = {'generation':'123','state':'ready','expiresAt':'2000-01-01T00:00:00+00:00'}
    assert media.recording_view({}) == {'state':'unchecked','expiresAt':None}
    assert media.recording_view({'recording_availability':snapshot}, '124')['state'] == 'unchecked'
