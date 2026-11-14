"""Real SQL: owner drafts are private, replayable and incapable of sending."""
import uuid
from unittest.mock import Mock
import pytest
from sqlalchemy import select
from models.account_email import AccountEmail
from models.home_outreach import HomeCampaign
from models.home_service import HomeAccessAudit, HomeCommand
from services import database, account_email
from tests.test_home_visits import app, home_db, headers

ROOT = '/api/home/outreach'


def content(**changes):
    return {'action':'save', 'subject':'A little help with dinner', 'body':'Good food. A tidy kitchen.',
        'postalAddress':'', 'design':{'image':'dinner','destination':'enroll'}, **changes}


def test_only_verified_owner_can_read_save_or_export(app, monkeypatch):
    monkeypatch.setenv('HOME_PUBLIC_URL', 'https://home.example.test')
    client = app.test_client()
    for actor in ('customer','helper','operator','unverified'):
        for method, path, body in [('GET',ROOT,None), ('POST',ROOT,content()),
                ('POST',ROOT+'/email-preview',{k:v for k,v in content().items() if k!='action'})]:
            assert client.open(path,method=method,json=body,headers=headers(actor,uuid.uuid4().hex)).status_code == 403
    assert client.get(ROOT).status_code == 401
    with database.db_session() as session:
        assert session.query(HomeCampaign).count() == 0


def test_draft_replay_revision_trash_and_audit_never_enqueue_mail(app, monkeypatch):
    sender = Mock(side_effect=AssertionError('Outreach must never send'))
    monkeypatch.setattr(account_email, 'send_account_message', sender)
    client = app.test_client(); key = uuid.uuid4().hex
    response = client.post(ROOT,json=content(),headers=headers('owner',key))
    assert response.status_code == 200, response.json
    assert client.post(ROOT,json=content(),headers=headers('owner',key)).json == response.json
    row = response.json
    path = ROOT+'/'+row['id']
    changed = client.put(path,json=content(revision=row['revision'],subject='New headline'),headers=headers('owner',uuid.uuid4().hex))
    assert changed.status_code == 200
    stale = client.put(path,json={'action':'trash','revision':row['revision']},headers=headers('owner',uuid.uuid4().hex))
    assert stale.status_code == 409
    revision = changed.json['revision']
    trashed = client.put(path,json={'action':'trash','revision':revision},headers=headers('owner',uuid.uuid4().hex))
    assert trashed.status_code == 200
    restored = client.put(path,json={'action':'restore','revision':trashed.json['revision']},headers=headers('owner',uuid.uuid4().hex))
    assert restored.status_code == 200
    rows = client.get(ROOT,headers=headers('owner')).json['drafts']
    assert len(rows)==1 and rows[0]['subject']=='New headline' and rows[0]['status']=='draft'
    with database.db_session() as session:
        assert session.query(AccountEmail).count()==0
        assert session.query(HomeCampaign).count()==1
        assert len(session.query(HomeAccessAudit).filter(HomeAccessAudit.action=='outreach_save').all())==2
        assert all(set(row.result)=={'id','revision'} for row in session.query(HomeCommand).all())
    sender.assert_not_called()


@pytest.mark.parametrize('changes', [
    {'subject':'Hello\r\nBcc: other@example.test'}, {'body':'x'*3001},
    {'design':{'image':'https://other.example/pixel','destination':'enroll'}},
    {'design':{'image':'dinner','destination':'javascript:alert(1)'}},
    {'design':{'image':'dinner','destination':'enroll','tracking':'on'}},
    {'action':'schedule'}, {'recipients':['customer@example.test']}, {'nextRunAt':'2030-01-01'},
])
def test_invalid_owner_input_rolls_back_without_scheduling_or_contact_imports(app, changes):
    response = app.test_client().post(ROOT,json=content(**changes),headers=headers('owner',uuid.uuid4().hex))
    assert response.status_code==400, response.json
    with database.db_session() as session:
        assert session.query(HomeCampaign).count()==0 and session.query(AccountEmail).count()==0


def test_email_export_escapes_text_requires_address_and_uses_fixed_destinations(app,monkeypatch):
    monkeypatch.setenv('HOME_PUBLIC_URL','https://home.example.test')
    client=app.test_client();body={k:v for k,v in content().items() if k!='action'}
    assert client.post(ROOT+'/email-preview',json=body,headers=headers('owner')).status_code==400
    body.update(body='<script>alert("no")</script>',postalAddress='Private business mailbox')
    response=client.post(ROOT+'/email-preview',json=body,headers=headers('owner'))
    assert response.status_code==200,response.json
    markup=response.json['html']
    assert '<script>' not in markup and '&lt;script&gt;' in markup
    assert 'https://home.example.test/#enroll' in markup
    assert '/assets/home-dinner.jpg' in markup
    assert 'mailto:connectwithus@cookcredit.com?subject=Unsubscribe' in markup
    assert 'Private business mailbox' in markup
    assert 'eassefa@' not in markup and 'photographer' not in markup
    with database.db_session() as session:
        assert session.query(AccountEmail).count()==0 and session.query(HomeCampaign).count()==0


def test_draft_cursor_is_bounded_and_invalid_cursor_has_safe_error(app):
    client=app.test_client()
    assert client.get(ROOT+'?cursor=not-a-uuid',headers=headers('owner')).status_code==400
    assert client.put(ROOT+'/'+str(uuid.uuid4()),json=content(revision=1),headers=headers('owner',uuid.uuid4().hex)).status_code==404
