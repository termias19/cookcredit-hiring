"""Durable invitations, included seat reservations and isolated concurrency."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from models import Org, OrgInvitation, User, OrgMembership
from models.account_email import AccountEmail
from services import database, account_email, email_capacity
from services.workspace_invitation_mail import deliver_invitation
from tests.test_hiring_postgres import db, client, headers


def included(monkeypatch):
    monkeypatch.setenv('FRONTEND_URL', 'http://localhost:5173')
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '1')


def invite(client, email='new@example.test', uid='employer'):
    return client.post('/business/team/invitations', headers=headers(uid), json={'email': email, 'seatRole': 'recruiter'})


def test_queue_is_atomic_encrypted_and_provider_is_not_called_on_request(db, client, monkeypatch):
    included(monkeypatch)
    monkeypatch.setattr(account_email, 'send_account_message', lambda *a: pytest.fail('request must not call provider'))
    response = invite(client)
    assert response.status_code == 201 and response.json['invitation']['emailQueued']
    token = response.json['invitation']['inviteUrl'].rsplit('/', 1)[1]
    with database.db_session() as session:
        queued = session.query(AccountEmail).one()
        invitation = session.query(OrgInvitation).one()
        assert queued.invitation_id == invitation.id
        assert token not in queued.invitation_token_ciphertext
        assert invitation.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert invite(client).status_code == 409
    with database.db_session() as session:
        assert session.query(AccountEmail).count() == 1


def test_concurrent_invitations_cannot_exceed_five_seats(db, client, monkeypatch):
    included(monkeypatch)
    def create(index):
        with client.application.test_client() as thread_client:
            return invite(thread_client, f'new{index}@example.test').status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(create, range(8)))
    # Fixture has an admin and viewer: only three seats remain.
    assert statuses.count(201) == 3
    assert statuses.count(409) == 5
    with database.db_session() as session:
        assert session.query(OrgInvitation).filter_by(status='pending').count() == 3
        assert session.query(AccountEmail).count() == 3
    assert invite(client, 'viewer-attempt@example.test', uid='viewer').status_code == 403


def test_queue_full_rolls_back_invitation_and_reservation(db, client, monkeypatch):
    included(monkeypatch)
    def full(*args): raise email_capacity.EmailQueueBusy('queue full')
    monkeypatch.setattr('services.workspace_invitation_mail.reserve_email_slot', full)
    with pytest.raises(email_capacity.EmailQueueBusy): invite(client)
    with database.db_session() as session:
        assert session.query(OrgInvitation).count() == 0


def test_delivery_uses_shared_provider_and_drops_secret_after_success(db, client, monkeypatch):
    included(monkeypatch)
    response = invite(client)
    link = response.json['invitation']['inviteUrl']
    sent = []
    monkeypatch.setenv('FRONTEND_URL', 'http://localhost:5173')
    monkeypatch.setattr(account_email, 'send_account_message', lambda *args: sent.append(args))
    assert account_email.dispatch_account_emails()['sent'] == 1
    assert sent[0][0] == 'new@example.test'
    assert link in sent[0][2] and link in sent[0][3]
    with database.db_session() as session:
        assert session.query(AccountEmail).one().invitation_token_ciphertext is None
    assert account_email.dispatch_account_emails()['claimed'] == 0


@pytest.mark.parametrize('state', ['revoked', 'expired', 'accepted'])
def test_inactive_invitation_never_sends(db, client, monkeypatch, state):
    included(monkeypatch)
    invite(client)
    with database.db_session() as session:
        row = session.query(OrgInvitation).one()
        row.status = state
    monkeypatch.setattr(account_email, 'send_account_message', lambda *a: pytest.fail('inactive invitation sent'))
    assert account_email.dispatch_account_emails()['skipped'] == 1


def test_retry_retains_same_token_without_duplicate_invitation(db, client, monkeypatch):
    included(monkeypatch)
    invite(client)
    def fail(*a): raise RuntimeError('provider failed')
    monkeypatch.setattr(account_email, 'send_account_message', fail)
    assert account_email.dispatch_account_emails()['failed'] == 1
    with database.db_session() as session:
        row = session.query(AccountEmail).one()
        cipher = row.invitation_token_ciphertext
        assert row.status == 'pending' and cipher
        row.available_at -= timedelta(hours=2)
    monkeypatch.setattr(account_email, 'send_account_message', lambda *a: None)
    assert account_email.dispatch_account_emails()['sent'] == 1
    with database.db_session() as session:
        assert session.query(OrgInvitation).count() == 1


def test_owner_approval_is_not_bypassed_by_team_invitation(db, client, monkeypatch):
    included(monkeypatch)
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setattr('services.hiring_access.access_allowed', lambda email, **kw: email == 'employer@example.test')
    created = invite(client)
    assert created.status_code == 201
    token = created.json['invitation']['inviteUrl'].rsplit('/', 1)[1]
    response = client.post('/business/team/invitations/accept', headers=headers('new'), json={'token': token})
    assert response.status_code == 403 and response.json['code'] == 'staging_access_denied'


def test_accepted_link_does_not_recreate_a_removed_member(db, client, monkeypatch):
    included(monkeypatch)
    with database.db_session() as session:
        session.add(User(id='new',email='new@example.test',name='New',roles=['eater']))
    token=invite(client).json['invitation']['inviteUrl'].rsplit('/',1)[1]
    assert client.post('/business/team/invitations/accept',headers=headers('new'),json={'token':token}).status_code == 200
    with database.db_session() as session:
        session.query(OrgMembership).filter_by(user_id='new').delete()
    assert client.post('/business/team/invitations/accept',headers=headers('new'),json={'token':token}).status_code == 409
    with database.db_session() as session:
        assert session.query(OrgMembership).filter_by(user_id='new').count() == 0


def test_staging_invitation_mail_stays_with_explicit_test_recipients(db, client, monkeypatch):
    included(monkeypatch)
    invite(client)
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','staging')
    monkeypatch.setenv('AUTH_EMAIL_TEST_RECIPIENTS','controlled@example.test')
    monkeypatch.setattr(account_email, 'send_account_message', lambda *a: pytest.fail('unapproved staging recipient'))
    assert account_email.dispatch_account_emails()['skipped'] == 1
