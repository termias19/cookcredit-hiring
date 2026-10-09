"""Approval inheritance must remain tenant-bound and immediately revocable."""
import hashlib
from datetime import datetime, timedelta, timezone
import pytest
from models import User, Org, OrgMembership, OrgInvitation
from models.hiring_access import HiringAccessRequest
from services import database, hiring_access
from tests.test_workspace_security import db
from tests.test_hiring_postgres import client, headers


@pytest.fixture
def approved(db, monkeypatch):
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setenv('STAGING_ALLOWED_EMAILS', '')
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '1')
    with database.db_session() as s:
        s.get(Org, db.org).created_by = 'employer'
        s.get(Org, db.other_org).created_by = 'other'
        s.add(HiringAccessRequest(email='employer@example.test', source='owner', status='approved'))
        s.add(User(id='new', email='new@example.test', name='New', roles=['eater']))
        s.add(OrgInvitation(org_id=db.org, invited_email='new@example.test', seat_role='hiring_manager',
            token_hash=hashlib.sha256(b'accept-test').hexdigest(), invited_by='employer',
            expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
    return db


def accept(client, uid='new'):
    return client.post('/business/team/invitations/accept', headers=headers(uid), json={'token':'accept-test'})


def test_invited_seat_is_not_independent_approval(client, approved):
    assert not hiring_access.employer_access_allowed('new@example.test', 'new')
    assert accept(client, 'viewer').status_code == 403
    assert accept(client).status_code == 200
    assert hiring_access.employer_access_allowed('new@example.test', 'new')
    assert not hiring_access.access_allowed('new@example.test')
    assert client.get('/business/org', headers=headers('new')).json['org']['id'] == str(approved.org)
    assert client.get('/business/team', headers=headers('new')).json['canManage'] is False
    assert client.post('/business/team/invitations', headers=headers('new'), json={'email':'outsider@example.test','seatRole':'admin'}).status_code == 403
    assert client.get('/business/activity', headers=headers('new')).status_code == 403
    assert accept(client).status_code == 200
    with database.db_session() as s:
        s.query(OrgMembership).filter_by(user_id='new').delete()
    assert not hiring_access.employer_access_allowed('new@example.test', 'new')
    assert accept(client).status_code == 409
    assert client.post('/business/activate', headers=headers('new'), json={'name':'Unapproved'}).status_code == 403


@pytest.mark.parametrize('target', ['employer', 'new'])
def test_platform_revocation_blocks_join_and_existing_session(client, approved, target):
    assert accept(client).status_code == 200
    with database.db_session() as s:
        row = s.query(HiringAccessRequest).filter_by(email=target+'@example.test').one_or_none()
        if row: row.status = 'revoked'
        else: s.add(HiringAccessRequest(email=target+'@example.test', source='owner', status='revoked'))
    assert not hiring_access.employer_access_allowed('new@example.test', 'new')
    assert client.get('/business/org', headers=headers('new')).status_code == 403
    assert accept(client).status_code == 403


@pytest.mark.parametrize('invalid', ['expired', 'revoked', 'unapproved', 'full'])
def test_invitation_constraints(client, approved, invalid):
    with database.db_session() as s:
        invitation = s.query(OrgInvitation).one()
        if invalid == 'expired': invitation.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
        elif invalid == 'revoked': invitation.status = 'revoked'
        elif invalid == 'unapproved': s.get(Org, approved.org).created_by = 'other'
        else:
            s.get(Org, approved.org).subscription_limits = {'teamSeats': 2}
    if invalid == 'full':
        # Exercise the endpoint's seat recheck independently of plan pricing.
        from unittest.mock import patch
        with patch('routes.business.team_access', return_value={'enabled':True, 'seatLimit':2}):
            assert accept(client).status_code == 409
    else: assert accept(client).status_code in (403,409)
    with database.db_session() as s:
        assert s.query(OrgMembership).filter_by(user_id='new').count() == 0


def test_unverified_and_cross_workspace_accounts_cannot_join(client, approved, monkeypatch):
    from middleware import auth
    monkeypatch.setattr(auth, '_verify_token', lambda token: {'uid':'new', 'email':'new@example.test', 'email_verified':False})
    assert accept(client).status_code == 403
    monkeypatch.setattr(auth, '_verify_token', lambda token: {'uid':'new', 'email':'new@example.test', 'email_verified':True})
    with database.db_session() as s:
        s.add(OrgMembership(org_id=approved.other_org, user_id='new', seat_role='viewer'))
    assert accept(client).status_code == 409
    with database.db_session() as s:
        assert s.query(OrgMembership).filter_by(user_id='new', org_id=approved.org).count() == 0
