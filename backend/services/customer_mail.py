"""Bounded customer mail on the existing scheduler, transport and outbox."""
import hashlib
import os
import uuid
from datetime import timedelta
from urllib.parse import urlencode
from sqlalchemy.dialects.postgresql import insert
from models.account_email import AccountEmail
from models.customer_mail import Campaign, EmailPreference, now
from services.database import db_session


def base_url():
    return os.environ['FRONTEND_URL'].split(',')[0].rstrip('/')


def enqueue_invoice_email(session, org, invoice, event_type):
    from models import User
    from services.email_capacity import reserve_email_slot
    owner = session.get(User, org.created_by) if org.created_by else None
    if not owner or not invoice.get('id'):
        return
    kind = 'billing_paid' if event_type == 'invoice.paid' else 'billing_failed'
    key = hashlib.sha256(f'{kind}:{invoice["id"]}'.encode()).hexdigest()
    if not reserve_email_slot(session, key):
        return
    session.execute(insert(AccountEmail).values(id=uuid.uuid4(), dedupe_key=key,
        kind=kind, recipient=owner.email, user_id=owner.id, status='pending',
        attempts=0, created_at=now(), available_at=now(),
        content={'orgId': str(org.id), 'invoiceId': str(invoice['id'])})
        .on_conflict_do_nothing(index_elements=['dedupe_key']))


def expand_due_campaigns():
    """At most ten offers per scheduler tick; reserve room for account mail."""
    from sqlalchemy import text
    from services.email_capacity import LOCK_ID
    with db_session() as session:
        # Same lock as transactional mail reservations; never exceed its cap.
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': LOCK_ID})
        backlog = session.query(AccountEmail.id).filter(AccountEmail.status.in_(('pending', 'sending'))).limit(20).count()
        if backlog >= 20:
            return 0
        # The shared Workspace mailbox also sends account mail. A quiet queue
        # alone does not imply daily provider capacity is available.
        recent = session.query(AccountEmail.id).filter(AccountEmail.created_at >= now()-timedelta(days=1))
        if recent.limit(250).count() >= 250:
            return 0
        offer_budget = 100 - recent.filter(AccountEmail.kind == 'campaign').limit(100).count()
        if offer_budget <= 0:
            return 0
        row = (session.query(Campaign).filter(Campaign.status == 'scheduled',
               Campaign.next_run_at <= now()).order_by(Campaign.next_run_at)
               .with_for_update(skip_locked=True).first())
        if not row:
            return 0
        if row.run_at is None:
            row.run_at = now()
            row.cursor = None
        query = session.query(EmailPreference).filter(EmailPreference.opted_in.is_(True),
                                                     EmailPreference.updated_at <= row.run_at)
        if row.cursor:
            query = query.filter(EmailPreference.user_id > row.cursor)
        subscribers = query.order_by(EmailPreference.user_id).limit(min(10, 20-backlog, offer_budget)).all()
        for sub in subscribers:
            key = hashlib.sha256(f'campaign:{row.id}:{row.run_at.isoformat()}:{sub.user_id}'.encode()).hexdigest()
            session.execute(insert(AccountEmail).values(id=uuid.uuid4(), dedupe_key=key,
                kind='campaign', recipient=sub.email, user_id=sub.user_id, status='pending',
                attempts=0, available_at=now(), created_at=now(),
                content={'campaignId': str(row.id), 'revision': row.revision,
                         'consentAt': sub.updated_at.isoformat()})
                .on_conflict_do_nothing(index_elements=['dedupe_key']))
            row.cursor = sub.user_id
        if not subscribers:
            row.run_at = None
            row.cursor = None
            row.status = 'scheduled' if row.interval_days else 'complete'
            row.next_run_at = now() + timedelta(days=row.interval_days) if row.interval_days else None
        return len(subscribers)


def deliver_customer_email(item):
    from services.account_email import account_email_content, send_account_message, get_auth
    content = item.content or {}
    # Do not send to a stale address after an account email change.
    provider = get_auth()
    try:
        user = provider.get_user(item.user_id)
    except provider.UserNotFoundError:
        return 'skipped'
    if user.disabled or not user.email_verified or (user.email or '').casefold() != item.recipient.casefold():
        return 'skipped'
    link = base_url() + '/business/profile?section=billing'
    headers = None
    if item.kind == 'campaign':
        with db_session() as session:
            sub = session.get(EmailPreference, item.user_id)
            row = session.get(Campaign, uuid.UUID(content['campaignId']))
            if (not sub or not sub.opted_in or sub.email.casefold() != item.recipient.casefold()
                    or sub.updated_at.isoformat() != content.get('consentAt') or not row
                    or row.status not in ('scheduled', 'complete')
                    or row.revision != content.get('revision') or not row.postal_address.strip()):
                return 'skipped'
            link = base_url() + '/email/unsubscribe?' + urlencode({'token': sub.unsubscribe_token})
            endpoint = os.environ['PUBLIC_API_URL'].rstrip('/') + '/api/customer-mail/unsubscribe?' + urlencode({'token': sub.unsubscribe_token})
            headers = {'List-Unsubscribe': '<' + endpoint + '>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}
            custom = (row.subject, row.subject, row.body, 'Unsubscribe from offers',
                      'Advertisement from CookCredit. You opted in to Hiring news and offers. '
                      'Unsubscribing does not affect account or payment emails.\n' + row.postal_address)
    else:
        paid = item.kind == 'billing_paid'
        # Obtain the current invoice so a delayed failure notice cannot follow payment.
        from services.stripe_service import retrieve_billing_invoice
        from models import Org
        invoice = retrieve_billing_invoice(content['invoiceId'])
        with db_session() as session:
            org = session.get(Org, uuid.UUID(content['orgId']))
            customer = invoice.get('customer')
            customer = customer.get('id') if hasattr(customer, 'get') else customer
            if not org or customer != org.stripe_customer_id:
                return 'skipped'
        if not paid and invoice.get('paid'):
            return 'skipped'
        if paid and not invoice.get('paid'):
            raise RuntimeError('invoice_payment_not_confirmed')
        title = 'Your CookCredit Hiring payment is confirmed' if paid else 'Your CookCredit Hiring payment needs attention'
        body = ('Thank you. Your subscription invoice has been paid. View the invoice and manage your subscription in Plans & billing.'
                if paid else 'We could not collect your subscription payment. Open Plans & billing to review the invoice and update your payment method.')
        custom = (title, title, body, 'Open Plans & billing',
                  'This is an account billing message. For help, contact connectwithus@cookcredit.com.')
    subject, plain, markup = account_email_content(item.kind, link, custom=custom)
    send_account_message(item.recipient, subject, plain, markup, headers=headers)
    return 'sent'
