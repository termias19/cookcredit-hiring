"""Real partner request persistence; auth, quota, encryption and delivery stubbed."""
import os
import pytest
from flask import Flask, g
from tests.test_report_playback_binding import db
from models import HiringApplication, PartnerInvitation
from services import database
from routes import partner

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local database required')


def test_default_motion_persists_and_replays_without_duplicate_request(db, monkeypatch):
    engine = database.SessionLocal.kw['bind']
    HiringApplication.__table__.create(engine)
    PartnerInvitation.__table__.create(engine)
    events, usage = [], []
    monkeypatch.setattr(partner, 'encrypt_webhook_secret', lambda value:value)
    monkeypatch.setattr(partner, 'decrypt_webhook_secret', lambda value:value)
    monkeypatch.setattr(partner, 'consume_request', lambda *a, **kw: usage.append(True) or {})
    monkeypatch.setattr(partner, 'emit_partner_event', lambda *a, **kw: events.append(kw))
    app = Flask(__name__)
    app.config['TESTING'] = True
    @app.before_request
    def identity():
        g.partner_org_id = db.org
        g.partner_environment = 'live'
    app.add_url_rule('/request', view_func=partner.create_assessment_request.__wrapped__, methods=['POST'])
    client = app.test_client()
    body = {'candidateEmail':'cook@example.test','externalJobId':'motion-default-job','jobTitle':'Prep cook'}
    headers = {'Idempotency-Key':'motion-default-test'}
    first = client.post('/request', json=body, headers=headers)
    assert first.status_code == 201
    data = first.json['data']
    assert data['assessmentProfile'] == 'wrist_motion'
    assert data['assessmentProfileVersion'] == 'knife-motion-v1'
    assert data['assessmentCriteria'] == {'profileVersion':'knife-motion-v1'}
    replay = client.post('/request', json={**body,'assessmentProfile':'wrist_motion',
        'assessmentProfileVersion':'knife-motion-v1'}, headers=headers)
    assert replay.status_code == 200
    assert replay.json['data']['id'] == data['id']
    conflict = client.post('/request', json={**body,'assessmentCriteria':{'minimumRhythm':90}}, headers=headers)
    assert conflict.status_code == 409
    with database.db_session() as session:
        rows = session.query(PartnerInvitation).all()
        assert len(rows) == 1
        assert rows[0].assessment_profile == 'wrist_motion'
        assert rows[0].request_config['assessmentCriteria'] == {'profileVersion':'knife-motion-v1'}
    assert len(usage) == 1
    assert len(events) == 2
