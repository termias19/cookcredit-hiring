import io
import uuid
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from services import hiring_cv

@pytest.mark.parametrize('value', [None, '', ' \n\t', 12, 'x' * 201, 'A\x00B'])
def test_name_required(value):
    with pytest.raises(ValueError): hiring_cv.full_name(value)

def test_unicode_and_mononyms_supported():
    assert hiring_cv.full_name('  Ermias  A  ') == 'Ermias A'
    assert hiring_cv.full_name('李') == '李'

@pytest.mark.parametrize('data', [b'', b'<html>fake PDF</html>', b'%PDF-1.4 missing end', b'x' * (hiring_cv.MAX_CV_BYTES + 1)], ids=['empty','html','truncated','oversized'])
def test_bad_or_oversized_cv_rejected(data):
    with pytest.raises(ValueError): hiring_cv.read_cv(SimpleNamespace(stream=io.BytesIO(data)))

def test_storage_bound_to_application_generation_and_hash(monkeypatch):
    aid=uuid.uuid4(); data=b'%PDF-1.4\nCV\n%%EOF'
    blob=Mock(generation=42);bucket=Mock();bucket.blob.return_value=blob
    monkeypatch.setattr(hiring_cv,'get_storage_bucket',lambda:bucket)
    meta=hiring_cv.store_cv(aid,data)
    assert meta['path'].startswith(f'hiring_cv/{aid}/')
    blob.upload_from_string.assert_called_once_with(data,content_type='application/pdf',if_generation_match=0,timeout=30)
    blob.download_as_bytes.return_value=data
    assert hiring_cv.download_cv(aid,meta)==data
    with pytest.raises(ValueError): hiring_cv.download_cv(uuid.uuid4(),meta)
    blob.download_as_bytes.return_value=b'changed'
    with pytest.raises(ValueError): hiring_cv.download_cv(aid,meta)


@pytest.mark.parametrize('commit', [False, True])
def test_uploaded_generation_deleted_only_on_transaction_rollback(monkeypatch, commit):
    from sqlalchemy.orm import Session
    blob=Mock(); bucket=Mock(); bucket.blob.return_value=blob
    monkeypatch.setattr(hiring_cv, 'get_storage_bucket', lambda: bucket)
    with Session() as session:
        session.begin()
        hiring_cv.cleanup_on_rollback(session, {'path':'hiring_cv/test/cv.pdf', 'generation':'42'})
        if commit: session.commit()
        else: session.rollback()
    if commit: blob.delete.assert_not_called()
    else: blob.delete.assert_called_once_with(if_generation_match=42, timeout=10)


def test_revoked_employer_cannot_use_applicant_cv_exemption(monkeypatch):
    from contextlib import contextmanager
    from flask import Flask
    from middleware import auth
    from routes import hiring
    from services import hiring_access
    aid = uuid.uuid4()
    application = SimpleNamespace(applicant_id='another-user')
    @contextmanager
    def db():
        yield SimpleNamespace(get=lambda *args: application)
    monkeypatch.setattr(hiring, 'db_session', db)
    monkeypatch.setattr(hiring_access, 'enabled', lambda: True)
    monkeypatch.setattr(hiring_access, 'access_allowed', lambda email: False)
    monkeypatch.setattr(auth, '_verify_token', lambda _: {
        'uid': 'revoked-employer', 'email': 'employer@example.test', 'email_verified': True})
    download = Mock()
    monkeypatch.setattr(hiring_cv, 'download_cv', download)
    app = Flask(__name__)
    app.register_blueprint(hiring.hiring_bp, url_prefix='/hiring')
    result = app.test_client().get(f'/hiring/applications/{aid}/cv', headers={'Authorization': 'Bearer test'})
    assert result.status_code == 404
    download.assert_not_called()


def test_expired_cv_is_not_advertised_or_downloaded(monkeypatch):
    from datetime import datetime, timedelta, timezone
    meta={'expiresAt':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
    assert not hiring_cv.available(meta)
    monkeypatch.setattr(hiring_cv,'get_storage_bucket',lambda:pytest.fail('No storage read after expiry'))
    with pytest.raises(hiring_cv.CvUnavailable):hiring_cv.download_cv('application',meta)


def test_legacy_cv_uses_application_submission_date():
    from datetime import datetime,timedelta,timezone
    meta={'path':'legacy'};now=datetime.now(timezone.utc)
    assert hiring_cv.available(meta,now-timedelta(days=29))
    assert not hiring_cv.available(meta,now-timedelta(days=30))


def test_missing_cv_has_terminal_unavailable_status(monkeypatch):
    from google.api_core.exceptions import NotFound
    digest='a'*64;meta={'path':f'hiring_cv/test/{digest}.pdf','sha256':digest,'generation':'1'}
    blob=Mock();blob.download_as_bytes.side_effect=NotFound('absent')
    bucket=Mock();bucket.blob.return_value=blob
    monkeypatch.setattr(hiring_cv,'get_storage_bucket',lambda:bucket)
    with pytest.raises(hiring_cv.CvUnavailable):hiring_cv.download_cv('test',meta)
