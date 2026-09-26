"""Role invitations persist the published contract; legacy requirements fail closed."""
import os
import pytest
from flask import Flask, g
from tests.test_report_playback_binding import db
from models import HiringApplication, PartnerInvitation, RolePosting
from services import database
from services.live_motion_evidence import hiring_motion_criteria
from routes import partner, hiring


def test_empty_criteria_has_no_invented_threshold():
    assert hiring_motion_criteria() == {'profileVersion': 'knife-motion-v1'}
    with pytest.raises(ValueError):
        hiring_motion_criteria({}, skill_floor=70)
    with pytest.raises(ValueError):
        hiring_motion_criteria({'minimumProductScore': 70})


@pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local database required')
@pytest.mark.parametrize('criteria', [None, {'profileVersion':'knife-motion-v1','minimumRhythm':80},
    {'profileVersion':'knife-motion-v1','minimumRhythm':60,'maximumRhythm':90,'minimumCadence':1.5,'maximumCadence':3.5}])
def test_role_invitation_freezes_motion_and_replays(db, monkeypatch, criteria):
    engine = database.SessionLocal.kw['bind']
    HiringApplication.__table__.create(engine)
    PartnerInvitation.__table__.create(engine)
    usage = []
    monkeypatch.setattr(partner, 'encrypt_webhook_secret', lambda value:value)
    monkeypatch.setattr(partner, 'decrypt_webhook_secret', lambda value:value)
    monkeypatch.setattr(partner, 'consume_request', lambda *a, **kw: usage.append(True) or {})
    with database.db_session() as session:
        session.get(RolePosting, db.role).requirements = {'assessmentCriteria': criteria}
    app = Flask(__name__)
    app.config['TESTING'] = True
    @app.before_request
    def identity():
        g.partner_org_id = db.org
        g.partner_environment = 'live'
    app.add_url_rule('/invite', view_func=partner.create_assessment_invitation.__wrapped__, methods=['POST'])
    client = app.test_client()
    body = {'roleId':str(db.role),'candidateEmail':'cook@example.test'}
    headers = {'Idempotency-Key':'role-motion-test'}
    first = client.post('/invite', json=body, headers=headers)
    assert first.status_code == 201, first.json
    expected = criteria or {'profileVersion':'knife-motion-v1'}
    with database.db_session() as session:
        session.get(RolePosting, db.role).requirements = {'assessmentCriteria':{'minimumProductScore':70}}
    replay = client.post('/invite', json=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json['data']['id'] == first.json['data']['id']
    rejected = client.post('/invite', json=body, headers={'Idempotency-Key':'legacy-role-test'})
    assert rejected.status_code == 409
    assert rejected.json['code'] == 'assessment_contract_review_required'
    foreign = client.post('/invite', json={**body,'roleId':str(db.other_role)}, headers=headers)
    assert foreign.status_code == 404
    with database.db_session() as session:
        invitation = session.query(PartnerInvitation).one()
        assert invitation.assessment_profile == 'wrist_motion'
        assert invitation.assessment_profile_version == 'knife-motion-v1'
        assert invitation.request_config['assessmentCriteria'] == expected
    assert len(usage) == 1


@pytest.mark.parametrize('criteria', [None, {'minimumProductScore':70}, {'profileVersion':'knife-motion-v1'}])
def test_application_contract_rejects_legacy_invitation(criteria):
    from types import SimpleNamespace
    from unittest.mock import Mock
    session = Mock()
    invitation = SimpleNamespace(assessment_profile='guillotine_dice', assessment_profile_version='knife-dice-v1')
    session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = invitation
    with pytest.raises(ValueError):
        hiring._application_motion_criteria(session, SimpleNamespace(id='test', assessment_criteria=criteria))
    invitation.assessment_profile = 'wrist_motion'
    invitation.assessment_profile_version = 'knife-motion-v1'
    if criteria != {'minimumProductScore':70}:
        assert hiring._application_motion_criteria(session, SimpleNamespace(id='test', assessment_criteria=criteria)) == {'profileVersion':'knife-motion-v1'}

@pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local database required')
@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('with_capture', [False, True])
def test_completion_contract_before_import_and_replay(db, monkeypatch, legacy, with_capture):
    import inspect, uuid
    from datetime import datetime, timedelta, timezone
    from unittest.mock import Mock
    from models import HiringAssessmentSession, HiringApplicationEvent, SkillAttempt, SkillAttemptEvent
    engine = database.SessionLocal.kw['bind']
    for model in (HiringApplication, PartnerInvitation, HiringAssessmentSession, HiringApplicationEvent, SkillAttemptEvent):
        model.__table__.create(engine)
    aid, sid = uuid.uuid4(), uuid.uuid4()
    criteria = {'minimumProductScore':70} if legacy else {'profileVersion':'knife-motion-v1','minimumRhythm':80}
    with database.db_session() as session:
        session.add(HiringApplication(id=aid, role_posting_id=db.role, applicant_id='cook', consent_version='test', assessment_criteria=criteria))
        session.flush()
        session.add(HiringAssessmentSession(id=sid, application_id=aid, applicant_id='cook', slot=1, expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
    verifier = Mock(return_value={'metadata':{},'storagePath':'test/recording.webm','generation':'123',
        'assessmentId':'test-recording', 'onDevice':{'score':90,'metrics':{}},'locator':'https://example.test/owned'})
    monkeypatch.setattr(hiring, 'verified_engine_assessment', verifier)
    monkeypatch.setattr(hiring.engine_recording_import, 'enabled', lambda:False)
    monkeypatch.setattr(hiring, 'emit_partner_event', lambda *a, **kw:None)
    monkeypatch.setattr(hiring, 'assessment_request_context', lambda *a:{})
    monkeypatch.setenv('ASSESSMENT_BRIDGE_ENABLED','1')
    app = Flask(__name__)
    app.config['TESTING'] = True
    @app.before_request
    def identity():
        g.user_id = 'cook'
    app.add_url_rule('/complete/<session_id>', view_func=inspect.unwrap(hiring.complete_attempt), methods=['POST'])
    client = app.test_client()
    from tests.test_hiring_capture import claim
    payload = {'assessmentId':'test-recording'}
    if with_capture:
        payload['captureMetadata'] = claim()
    if not legacy:
        invalid = client.post('/complete/'+str(sid), json={**payload, 'captureMetadata':{'serverVerified':True}})
        assert invalid.status_code == 400
        verifier.assert_not_called()
    response = client.post('/complete/'+str(sid), json=payload)
    if legacy:
        assert response.status_code == 409, response.json
        assert response.json['code'] == 'assessment_contract_review_required'
        verifier.assert_not_called()
    else:
        assert response.status_code == 202, response.json
        with database.db_session() as session:
            attempt = session.get(SkillAttempt, uuid.UUID(response.json['attemptId']))
            assert attempt.profile_id == 'wrist_motion'
            assert attempt.metadata_['assessment_profile_version'] == 'knife-motion-v1'
            assert attempt.metadata_['assessment_criteria'] == criteria
            stored_capture = attempt.metadata_.get('capture_evidence')
            if with_capture:
                assert stored_capture['capture'] == payload['captureMetadata']
                assert stored_capture['recordingGeneration'] == '123'
                assert stored_capture['serverVerified'] is False
            else:
                assert stored_capture is None
        repeated = client.post('/complete/'+str(sid), json={'assessmentId':'test-recording'})
        assert repeated.status_code == 200
        assert repeated.json['attemptId'] == response.json['attemptId']
        assert verifier.call_count == 1
        changed = client.post('/complete/'+str(sid), json={**payload, 'captureMetadata':{'serverVerified':True}})
        assert changed.status_code == 200
        with database.db_session() as session:
            attempt = session.get(SkillAttempt, uuid.UUID(response.json['attemptId']))
            assert attempt.metadata_.get('capture_evidence') == stored_capture
        assert verifier.call_count == 1

@pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local database required')
def test_public_default_matches_invitation_contract(db):
    from models import Org
    with database.db_session() as session:
        role = session.get(RolePosting, db.role)
        role.requirements = {}
        result = hiring._public_role(role, session.get(Org, db.org))
        assert result['assessment']['criteria'] == {'profileVersion':'knife-motion-v1'}


@pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local database required')
def test_motion_worker_never_calls_dice_scorer_or_certifies(db, monkeypatch):
    from models import SkillAttempt, SkillAttemptEvent
    from services import skill_attempts
    from unittest.mock import Mock
    SkillAttemptEvent.__table__.create(database.SessionLocal.kw['bind'])
    monkeypatch.setattr(skill_attempts, '_sync_hiring_if_linked', lambda *a:None)
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.profile_id = 'wrist_motion'
        attempt.metadata_ = {'source':'cookcredit-skill-live','assessment_profile_version':'knife-motion-v1'}
        attempt.verification_state = 'VERIFYING'
        attempt.authoritative_score = 99
        attempt.tier = 'expert'
    scorer, fetcher = Mock(), Mock()
    result = skill_attempts.run_recompute(db.attempt, score_video=scorer, fetch_video=fetcher)
    assert result.verification_state == 'INSUFFICIENT'
    assert result.authoritative_score is None
    assert result.tier is None
    assert result.reconciliation['agreement'] == 'unverifiable'
    skill_attempts.run_recompute(db.attempt, score_video=scorer, fetch_video=fetcher)
    scorer.assert_not_called()
    fetcher.assert_not_called()
    with database.db_session() as session:
        assert session.query(SkillAttemptEvent).count() == 1
