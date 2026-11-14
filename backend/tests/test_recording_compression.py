"""Processing security/fencing against a disposable local PostgreSQL schema."""
import os
import uuid
from datetime import timedelta
from types import SimpleNamespace
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import User, Org, RolePosting, SkillAttempt, AssessmentShare
from services import database, recording_compression as compression

pytestmark = pytest.mark.skipif(not os.getenv('HIRING_TEST_DATABASE_URL'), reason='explicit local database required')


@pytest.fixture
def db(monkeypatch):
    url = os.environ['HIRING_TEST_DATABASE_URL']
    parsed = make_url(url)
    assert parsed.host in ('localhost', '127.0.0.1') and parsed.username == 'cookcredit_test'
    schema = 'compression_test_' + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public'})
    try:
        for model in (User, Org, RolePosting, SkillAttempt, AssessmentShare):
            model.__table__.create(engine)
        with engine.begin() as connection:
            migration = (Path(__file__).parents[1] / 'migrations/034_recording_compression.sql').read_text()
            connection.exec_driver_sql(migration)
            connection.exec_driver_sql(migration)
        monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
        ids = SimpleNamespace(role=uuid.uuid4(), attempt=uuid.uuid4())
        with database.db_session() as session:
            session.add(User(id='cook', email='synthetic@example.test', name='Synthetic'))
            session.flush()
            org = Org(name='Synthetic', created_by='cook')
            session.add(org); session.flush()
            session.add(RolePosting(id=ids.role, org_id=org.id, title='Synthetic'))
            session.add(SkillAttempt(id=ids.attempt, user_id='cook', session_id='synthetic',
                                     verification_state='VERIFIED', metadata_={}))
        yield ids
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


def prepare(db):
    stamp = compression.now()
    path = 'cookcredit-skill/users/cook/assessments/synthetic/recording.mp4'
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.metadata_ = {'source': 'cookcredit-skill-live', 'recording_path': path,
            'recording_generation': '123', 'recording_availability': {'generation': '123',
                'state': 'ready', 'expiresAt': (stamp + timedelta(days=1)).isoformat()}}
        session.add(AssessmentShare(role_posting_id=db.role, attempt_id=db.attempt, applicant_id='cook',
                                   storage_path=path, storage_generation='123', consent_version='test-v1'))
        compression.ensure_compression_intent(attempt)
    return path


def test_duplicate_dispatch_and_terminal_scoring_are_independent(db, monkeypatch):
    prepare(db)
    monkeypatch.setenv('HIRING_COMPRESSION_JOB', 'configured')
    sent = []
    assert compression.drain_compression(send=lambda *v: sent.append(v))['delivered'] == 1
    assert compression.drain_compression(send=lambda *v: sent.append(v))['claimed'] == 0
    assert len(sent) == 1
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.verification_state == 'VERIFIED' and attempt.dispatch_due_at is None
        assert attempt.compression_count == 1


def test_expired_lease_recovers_and_old_worker_cannot_publish(db):
    prepare(db)
    aid, old = compression._claim()
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.compression_lease_until = compression.now() - timedelta(seconds=1)
        attempt.compression_due_at = compression.now() - timedelta(seconds=1)
    aid, fresh = compression._claim()
    assert old != fresh
    assert not compression._finish(aid, old, 'ready', derivative={'wrong': True})
    assert compression.process_recording(aid, old) == 'stale'
    assert compression._finish(aid, fresh, 'ready', derivative={'correct': True})
    with database.db_session() as session:
        assert session.get(SkillAttempt, db.attempt).metadata_['playback_derivative'] == {'correct': True}


def test_revocation_and_retention_block_publish_without_deleting_original(db):
    path = prepare(db)
    aid, token = compression._claim()
    with database.db_session() as session:
        share = session.query(AssessmentShare).filter_by(attempt_id=db.attempt).one()
        share.revoked_at = compression.now()
    assert compression._finish(aid, token, 'ready', derivative={'wrong': True})
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.compression_state == 'skipped' and 'playback_derivative' not in attempt.metadata_
        assert attempt.metadata_['recording_path'] == path
        assert attempt.metadata_['recording_generation'] == '123'


def test_retry_exhaustion_alerts_and_preserves_assessment(db, monkeypatch, capsys):
    prepare(db)
    monkeypatch.setenv('HIRING_COMPRESSION_JOB', 'configured')
    def fail(*_): raise RuntimeError('token=NEVER-LOG-ME')
    for _ in range(3):
        compression.drain_compression(send=fail)
        with database.db_session() as session:
            session.get(SkillAttempt, db.attempt).compression_due_at = compression.now() - timedelta(seconds=1)
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.compression_state == 'failed' and attempt.verification_state == 'VERIFIED'
        assert attempt.compression_count == 3
    logs = capsys.readouterr().out
    assert 'NEVER-LOG-ME' not in logs and 'execution_start_failed' in logs
    assert '"severity": "ERROR"' in logs and '"queue": "recording_compression"' in logs


def test_admission_is_bounded_and_source_without_consent_is_not_claimed(db, monkeypatch):
    prepare(db)
    monkeypatch.setenv('HIRING_COMPRESSION_MAX_ACTIVE', '1')
    assert compression._claim()
    assert compression._claim() is None
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.compression_state = None
        attempt.compression_lease_until = None
        session.query(AssessmentShare).filter_by(attempt_id=db.attempt).one().revoked_at = compression.now()
    assert compression._claim() is None


def test_concurrent_metadata_merge_is_preserved(db):
    prepare(db)
    aid, token = compression._claim()
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.metadata_ = {**attempt.metadata_, 'unrelated_review': 'preserved'}
    compression._finish(aid, token, 'ready', derivative={'profile': compression.PROFILE})
    with database.db_session() as session:
        assert session.get(SkillAttempt, db.attempt).metadata_['unrelated_review'] == 'preserved'
