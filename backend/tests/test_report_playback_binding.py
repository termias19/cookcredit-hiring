"""Report/playback regression in isolated PostgreSQL evidence tables."""
import uuid
import os
from unittest.mock import Mock
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import pytest
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from models import (AssessmentShare, AssessmentAccessLog, CookProfile, SkillAttempt,
                    User, Org, OrgMembership, RolePosting, ResumeKeypoints)
from services import database
from services.database import db_session
from routes import business
from middleware import auth

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local test database required')


@pytest.fixture
def db(monkeypatch):
    url = os.environ['HIRING_TEST_DATABASE_URL']
    parsed = make_url(url)
    if parsed.host not in ('localhost', '127.0.0.1') or parsed.username != 'cookcredit_test':
        pytest.fail('Dedicated local test database required')
    schema = 'playback_test_' + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public'})
    # Spatial biography is unrelated to evidence selection. Keep assessment,
    # consent, company, role and access-log queries real; stub only biography.
    class EvidenceSession(Session):
        def get(self, entity, ident, **kwargs):
            if entity is CookProfile:
                return SimpleNamespace(bio='', cuisines=[], base_city='', years_experience=0,
                                       skill_verified=False, skill_score=None, skill_test_video_url=None)
            return super().get(entity, ident, **kwargs)
    try:
        for model in (User, Org, OrgMembership, RolePosting, SkillAttempt,
                      AssessmentShare, AssessmentAccessLog, ResumeKeypoints):
            model.__table__.create(engine)
        monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, class_=EvidenceSession, expire_on_commit=False))
        ids = SimpleNamespace(org=uuid.uuid4(), other_org=uuid.uuid4(), role=uuid.uuid4(), other_role=uuid.uuid4(), attempt=uuid.uuid4())
        with db_session() as session:
            for uid in ('cook', 'employer', 'other', 'viewer'):
                session.add(User(id=uid, email=uid+'@example.test', name=uid, roles=['business']))
            session.flush()
            session.add_all([Org(id=ids.org, name='Kitchen'), Org(id=ids.other_org, name='Other')])
            session.flush()
            session.add_all([OrgMembership(org_id=ids.org, user_id='employer', seat_role='admin'),
                             OrgMembership(org_id=ids.org, user_id='viewer', seat_role='viewer'),
                             OrgMembership(org_id=ids.other_org, user_id='other', seat_role='admin'),
                             RolePosting(id=ids.role, org_id=ids.org, title='Prep', status='open'),
                             RolePosting(id=ids.other_role, org_id=ids.other_org, title='Other', status='open'),
                             SkillAttempt(id=ids.attempt, user_id='cook', session_id='original', verification_state='VERIFIED')])
        yield ids
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(auth, '_verify_token', lambda token: {'uid':token, 'email':token+'@example.test', 'email_verified':True})
    monkeypatch.setattr(business, 'playback_url', lambda path, generation, uid: 'https://example.test/' + generation)
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    app.register_blueprint(business.business_bp, url_prefix='/business')
    return app.test_client()


def headers(uid):
    return {'Authorization':'Bearer '+uid}


def add_share(db, attempt):
    with db_session() as session:
        session.add(AssessmentShare(role_posting_id=db.role, attempt_id=attempt, applicant_id='cook',
                                   storage_path='skill_videos/cook/test.webm', storage_generation='123',
                                   consent_version='test'))


def two_attempts(db, client):
    add_share(db, db.attempt)
    newer = uuid.uuid4()
    now = datetime.now(timezone.utc)
    with db_session() as session:
        session.get(SkillAttempt, db.attempt).created_at = now - timedelta(days=2)
        session.add(SkillAttempt(id=newer, user_id='cook', session_id='newer-session',
                                verification_state='VERIFIED', authoritative_score=91,
                                metadata_={'recording_generation': '123'},
                                video_url='https://example.test/locator', created_at=now))
    add_share(db, newer)
    with db_session() as session:
        for share in session.query(AssessmentShare).all():
            share.granted_at = now + timedelta(days=1) if share.attempt_id == db.attempt else now
    return newer


@pytest.mark.parametrize('same_timestamp', [False, True])
def test_report_and_default_playback_ignore_reversed_share_dates(db, client, same_timestamp):
    newer = two_attempts(db, client)
    if same_timestamp:
        with db_session() as session:
            session.get(SkillAttempt, db.attempt).created_at = session.get(SkillAttempt, newer).created_at
    report = client.get('/business/candidate/cook/report', headers=headers('employer'))
    assert report.status_code == 200
    if not same_timestamp:
        assert report.json['assessment']['attemptId'] == str(newer)
    video = client.get('/business/candidate/cook/video', headers=headers('employer'))
    assert video.status_code == 200
    assert video.json['attemptId'] == report.json['assessment']['attemptId']
    assert video.headers['Cache-Control'] == 'no-store'
    assert video.json['expiresInSeconds'] == 300


@pytest.mark.parametrize('landmarks', ['', '&landmarks=1'])
def test_pinned_playback_never_falls_back_after_revocation(db, client, landmarks):
    newer = two_attempts(db, client)
    url = f'/business/candidate/cook/video?roleId={db.role}&attemptId={db.attempt}' + landmarks
    video = client.get(url, headers=headers('employer'))
    assert video.status_code == 200
    assert video.json['attemptId'] == str(db.attempt)
    with db_session() as session:
        share = session.query(AssessmentShare).filter_by(attempt_id=db.attempt).one()
        share.revoked_at = datetime.now(timezone.utc)
    assert client.get(url, headers=headers('employer')).status_code == 403
    assert client.get('/business/candidate/cook/video', headers=headers('employer')).json['attemptId'] == str(newer)


@pytest.mark.parametrize('landmarks', ['', '&landmarks=1'])
def test_pinned_playback_keeps_tenant_role_and_identity_boundaries(db, client, monkeypatch, landmarks):
    add_share(db, db.attempt)
    signer = Mock()
    monkeypatch.setattr(business, 'playback_url', signer)
    url = f'/business/candidate/cook/video?attemptId={db.attempt}' + landmarks
    for user in ('other', 'viewer'):
        assert client.get(url, headers=headers(user)).status_code == 403
    assert client.get(url + f'&roleId={db.other_role}', headers=headers('employer')).status_code == 403
    assert client.get(f'/business/candidate/other/video?attemptId={db.attempt}', headers=headers('employer')).status_code == 403
    assert client.get('/business/candidate/cook/video?attemptId=' + str(uuid.uuid4()), headers=headers('employer')).status_code == 403
    for invalid in ('bad', ''):
        assert client.get('/business/candidate/cook/video?attemptId=' + invalid, headers=headers('employer')).status_code == 400
    signer.assert_not_called()
    with db_session() as session:
        assert session.query(AssessmentAccessLog).count() == 0
