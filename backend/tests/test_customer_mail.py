import os
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_hiring_postgres import db, client, headers
from models import Org
from models.account_email import AccountEmail
from models.customer_mail import Campaign, EmailPreference, CampaignEvent, now
from routes.customer_mail import customer_mail_bp
from services import account_email, customer_mail, database, hiring_access, stripe_service

pytestmark = pytest.mark.skipif(not os.getenv('HIRING_TEST_DATABASE_URL'), reason='isolated PostgreSQL required')


@pytest.fixture
def mail_client(client, monkeypatch):
    client.application.register_blueprint(customer_mail_bp, url_prefix='/mail')
    monkeypatch.setattr(hiring_access, 'enabled', lambda: True)
    monkeypatch.setenv('STAGING_ALLOWED_EMAILS', 'employer@example.test')
    monkeypatch.setattr(hiring_access, 'is_owner', lambda email, verified=True: verified and email == 'employer@example.test')
    monkeypatch.setenv('FRONTEND_URL', 'https://hiring.example.test')
    monkeypatch.setenv('PUBLIC_API_URL', 'https://api.example.test')
    monkeypatch.setattr(account_email, 'get_auth', lambda: SimpleNamespace(
        get_user=lambda uid: SimpleNamespace(email=uid+'@example.test', email_verified=True, disabled=False)))
    return client


def draft(client):
    response = client.post('/mail/owner/campaigns', headers=headers('employer'), json={
        'subject': 'Hiring news', 'body': 'An optional update', 'postalAddress': 'Test-only address', 'intervalDays': 7})
    assert response.status_code == 200
    return response.json['campaign']


def due(row):
    with database.db_session() as session:
        c = session.get(Campaign, uuid.UUID(row['id']))
        c.status = 'scheduled'
        c.next_run_at = now() - timedelta(seconds=1)


def opt_in(client):
    assert client.put('/mail/preferences', headers=headers('cook'), json={'offers': True}).status_code == 200


def test_owner_only_revision_guard_and_recoverable_trash(mail_client):
    assert mail_client.get('/mail/owner/campaigns', headers=headers('cook')).status_code == 403
    row = draft(mail_client)
    uri = '/mail/owner/campaigns/' + row['id']
    assert mail_client.put(uri, headers=headers('employer'), json={**row, 'action': 'trash'}).json['campaign']['status'] == 'trashed'
    assert mail_client.put(uri, headers=headers('employer'), json={**row, 'action': 'restore'}).status_code == 409
    row['revision'] += 1
    assert mail_client.put(uri, headers=headers('employer'), json={**row, 'action': 'restore'}).json['campaign']['status'] == 'draft'
    with database.db_session() as session:
        assert session.query(CampaignEvent).count() == 3


def test_preferences_default_off_and_unsubscribe_prevents_queued_send(mail_client, monkeypatch):
    assert mail_client.get('/mail/preferences', headers=headers('cook')).json == {'offers': False}
    opt_in(mail_client)
    row = draft(mail_client); due(row)
    assert customer_mail.expand_due_campaigns() == 1
    with database.db_session() as session:
        token = session.get(EmailPreference, 'cook').unsubscribe_token
        queued = session.query(AccountEmail).filter_by(kind='campaign').one()
    assert mail_client.get('/mail/unsubscribe?token='+token).status_code == 405
    assert mail_client.post('/mail/unsubscribe?token='+token, data={'List-Unsubscribe': 'One-Click'}).status_code == 200
    sender = Mock(); monkeypatch.setattr(account_email, 'send_account_message', sender)
    assert customer_mail.deliver_customer_email(queued) == 'skipped'
    sender.assert_not_called()
    # Re-subscribing must not revive offers queued before the unsubscribe.
    opt_in(mail_client)
    assert customer_mail.deliver_customer_email(queued) == 'skipped'


def test_campaign_retry_deduplication_and_priority_reserve(mail_client):
    opt_in(mail_client)
    row = draft(mail_client); due(row)
    assert customer_mail.expand_due_campaigns() == 1
    assert customer_mail.expand_due_campaigns() == 0
    with database.db_session() as session:
        assert session.query(AccountEmail).filter_by(kind='campaign').count() == 1
        c = session.get(Campaign, uuid.UUID(row['id']))
        assert c.next_run_at > now() + timedelta(days=6)
        c.next_run_at = now() - timedelta(seconds=1)
        for i in range(19):
            session.add(AccountEmail(dedupe_key=str(i), kind='verify', recipient='cook@example.test'))
    assert customer_mail.expand_due_campaigns() == 0


def test_campaign_daily_budget_preserves_mailbox_headroom(mail_client):
    opt_in(mail_client); row = draft(mail_client); due(row)
    with database.db_session() as session:
        for i in range(100):
            session.add(AccountEmail(dedupe_key='daily-'+str(i), kind='campaign',
                                     recipient='cook@example.test', status='sent'))
    assert customer_mail.expand_due_campaigns() == 0


@pytest.mark.parametrize('action', ['pause', 'trash', 'save'])
def test_owner_change_suppresses_unsent_old_revision(mail_client, monkeypatch, action):
    opt_in(mail_client); row = draft(mail_client); due(row)
    customer_mail.expand_due_campaigns()
    with database.db_session() as session:
        queued = session.query(AccountEmail).filter_by(kind='campaign').one()
    assert mail_client.put('/mail/owner/campaigns/'+row['id'], headers=headers('employer'), json={**row, 'action': action}).status_code == 200
    monkeypatch.setattr(account_email, 'send_account_message', lambda *a, **k: pytest.fail('Suppressed campaign sent'))
    assert customer_mail.deliver_customer_email(queued) == 'skipped'


def test_offer_html_escaped_and_one_click_headers(mail_client, monkeypatch):
    opt_in(mail_client); row = draft(mail_client); due(row)
    with database.db_session() as session:
        session.get(Campaign, uuid.UUID(row['id'])).body = '<script>alert(1)</script>'
    customer_mail.expand_due_campaigns()
    with database.db_session() as session:
        queued = session.query(AccountEmail).filter_by(kind='campaign').one()
    sender = Mock(); monkeypatch.setattr(account_email, 'send_account_message', sender)
    assert customer_mail.deliver_customer_email(queued) == 'sent'
    assert '<script>' not in sender.call_args.args[3]
    assert '&lt;script&gt;' in sender.call_args.args[3]
    assert sender.call_args.kwargs['headers']['List-Unsubscribe-Post'] == 'List-Unsubscribe=One-Click'


def test_schedule_requires_address_and_future_time(mail_client):
    row = draft(mail_client)
    path = '/mail/owner/campaigns/'+row['id']
    future = (now()+timedelta(hours=1)).isoformat()
    assert mail_client.put(path, headers=headers('employer'), json={**row, 'action': 'schedule', 'subject': 'Invalid edit', 'postalAddress': '', 'nextRunAt': future}).status_code == 400
    with database.db_session() as session:
        unchanged = session.get(Campaign, uuid.UUID(row['id']))
        assert unchanged.subject == row['subject'] and unchanged.postal_address == row['postalAddress']
    assert mail_client.put(path, headers=headers('employer'), json={**row, 'action': 'schedule', 'nextRunAt': 'invalid'}).status_code == 400
    assert mail_client.put(path, headers=headers('employer'), json={**row, 'action': 'schedule', 'nextRunAt': future}).json['campaign']['status'] == 'scheduled'


def test_invoice_mail_dedupes_and_skips_stale_failure(db, mail_client, monkeypatch):
    with database.db_session() as session:
        org = session.get(Org, db.org); org.created_by = 'employer'; org.stripe_customer_id = 'cus_hiring'
        for _ in range(2):
            customer_mail.enqueue_invoice_email(session, org, {'id': 'in_one'}, 'invoice.paid')
        customer_mail.enqueue_invoice_email(session, org, {'id': 'in_one'}, 'invoice.payment_failed')
    with database.db_session() as session:
        assert session.query(AccountEmail).count() == 2
        paid = session.query(AccountEmail).filter_by(kind='billing_paid').one()
        failed = session.query(AccountEmail).filter_by(kind='billing_failed').one()
    monkeypatch.setattr(stripe_service, 'retrieve_billing_invoice', lambda _: {'paid': True, 'customer': 'cus_hiring'})
    sender = Mock(); monkeypatch.setattr(account_email, 'send_account_message', sender)
    assert customer_mail.deliver_customer_email(failed) == 'skipped'
    assert customer_mail.deliver_customer_email(paid) == 'sent'
    assert sender.call_count == 1


def test_billing_outbox_failure_rolls_back_event_and_retries(db, mail_client, monkeypatch):
    from routes import stripe as billing
    from services.email_capacity import EmailQueueBusy
    monkeypatch.setenv('STRIPE_ASYNC_ENABLED', '1')
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    with database.db_session() as session:
        org = session.get(Org, db.org); org.created_by = 'employer'; org.stripe_customer_id = 'cus_hiring'; org.stripe_subscription_id = 'sub_hiring'
    event = {'id': 'evt_invoice', 'type': 'invoice.paid', 'livemode': False, 'data': {'object': {'id': 'in_one', 'customer': 'cus_hiring', 'subscription': 'sub_hiring'}}}
    monkeypatch.setattr(billing, 'construct_webhook_event', lambda *a: event)
    monkeypatch.setattr(billing, 'retrieve_billing_subscription', lambda _: {'id': 'sub_hiring', 'customer': 'cus_hiring', 'status': 'active', 'items': {'data': [{'price': {'id': 'price_team'}}]}})
    assert mail_client.post('/stripe/webhook', data=b'signed').json['queued']
    original = customer_mail.enqueue_invoice_email
    monkeypatch.setattr(customer_mail, 'enqueue_invoice_email', Mock(side_effect=EmailQueueBusy()))
    assert billing.dispatch_billing_events()['retrying'] == 1
    from models import StripeEvent
    with database.db_session() as session:
        receipt = session.get(StripeEvent, 'evt_invoice'); assert receipt.processed_at is None
        receipt.next_attempt_at = now() - timedelta(seconds=1)
    monkeypatch.setattr(customer_mail, 'enqueue_invoice_email', original)
    assert billing.dispatch_billing_events()['processed'] == 1
    with database.db_session() as session:
        assert session.query(AccountEmail).filter_by(kind='billing_paid').count() == 1
