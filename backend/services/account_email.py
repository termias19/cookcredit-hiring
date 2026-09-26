"""CookCredit account mail, with bounded retries and no action-code logging."""
import hashlib
import html
import os
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs, urlencode
import requests
from sqlalchemy import and_, or_
from sqlalchemy.dialects.postgresql import insert
from models.account_email import AccountEmail
from services.database import db_session
from services.firebase import get_auth
from services.runtime_config import deployment_environment


def utcnow():
    return datetime.now(timezone.utc)


def enqueue_account_email(session, *, kind, recipient, user_id=None):
    if kind not in {'verify', 'reset', 'welcome'}:
        raise ValueError('Unsupported account email')
    identity = user_id if kind == 'welcome' else recipient.strip().casefold()
    window = 'once' if kind == 'welcome' else str(int(utcnow().timestamp()) // 300)
    key = hashlib.sha256(f'{kind}:{identity}:{window}'.encode()).hexdigest()
    session.execute(insert(AccountEmail).values(
        id=uuid.uuid4(), dedupe_key=key, kind=kind, recipient=recipient,
        user_id=user_id, status='pending', attempts=0,
        created_at=utcnow(), available_at=utcnow()).on_conflict_do_nothing(index_elements=['dedupe_key']))


def account_email_content(kind, link):
    content = {
        'verify': ('Welcome to CookCredit — verify your email', 'Confirm your email address',
                   'Thank you for creating a CookCredit account. Confirm this email address to finish setting up your account.',
                   'Verify email', 'If you did not create a CookCredit account, you can ignore this message.'),
        'welcome': ('Your CookCredit account is ready', 'Welcome to CookCredit',
                    'Your email address is verified and your account is ready. Return to your application, or set up your company workspace to invite applicants and review their knife skills.',
                    'Open CookCredit', 'You are receiving this account confirmation because you signed up for CookCredit.'),
        'reset': ('Reset your CookCredit password', 'Choose a new password',
                  'We received a request to reset the password for your CookCredit account. Use the secure link below to choose a new password.',
                  'Reset password', 'If you did not request this, ignore this email. Your password will stay unchanged.'),
        'access_requested': ('CookCredit hiring access request', 'A hiring access request is waiting',
                             'Open your private owner queue to review the request. Receiving a request does not grant access.',
                             'Review access requests', 'Only the verified CookCredit owner can approve access.'),
        'access_approved': ('Your CookCredit hiring access is approved', 'Your hiring access is ready',
                            'Create an account or sign in using this email address, verify your email, and set up your own company workspace. Your team reviews assessment results and makes the hiring decisions. No subscription payment is required.',
                            'Open CookCredit hiring', 'This invitation follows an owner-approved request for hiring access. It does not add you to another company’s workspace.'),
    }
    subject, title, body, button, footer = content[kind]
    safe_link = html.escape(link, quote=True)
    # Use the same published mark as the account screens. PNG is intentional:
    # many inboxes do not render SVG images inside HTML email.
    logo_url = 'https://cookcredit.com/cookcredit-mark-orange.png'
    text = (f'{title}\n\n{body}\n\n{button}: {link}\n\n{footer}\n\nThe CookCredit team\n\n'
            'Privacy Policy: https://cookcredit.com/privacy.html\n'
            'Terms of Use: https://cookcredit.com/terms.html\n')
    markup = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f4f1ea;color:#252923;font-family:Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:auto;background:#fefdfb;border:1px solid #e3e0d9">
<tr><td style="padding:32px"><img src="{logo_url}" width="88" height="68" alt="CookCredit" style="display:block;border:0;margin:0 0 12px;width:88px;height:68px">
<p style="font-family:Georgia,serif;font-size:30px;margin:0 0 32px">CookCredit</p>
<h1 style="font-family:Georgia,serif;font-size:28px;font-weight:normal">{title}</h1>
<p style="line-height:1.7">{body}</p><p style="margin:28px 0"><a href="{safe_link}" style="display:inline-block;background:#1f6f5c;color:white;padding:14px 24px;text-decoration:none">{button}</a></p>
<p style="font-size:13px;color:#636960;line-height:1.7">{footer}</p>
<p style="line-height:1.7">The CookCredit team</p><p style="font-size:12px;line-height:1.6;color:#636960">Having trouble with the button? Copy this link into your browser:<br><a href="{safe_link}" style="color:#1f6f5c;word-break:break-all">{safe_link}</a></p>
<p style="font-size:12px;line-height:1.8;margin-top:24px"><a href="https://cookcredit.com/privacy.html" style="color:#636960">Privacy Policy</a> &nbsp;·&nbsp; <a href="https://cookcredit.com/terms.html" style="color:#636960">Terms of Use</a></p>
</td></tr></table></td></tr></table></body></html>'''
    return subject, text, markup


def _action_link(kind, recipient):
    base = os.environ['FRONTEND_URL'].split(',')[0].rstrip('/')
    provider = get_auth()
    settings = provider.ActionCodeSettings(url=f'{base}/login')
    raw = (provider.generate_email_verification_link(recipient, settings) if kind == 'verify'
           else provider.generate_password_reset_link(recipient, settings))
    params = parse_qs(urlsplit(raw).query)
    # Use the same branded Google-managed handler as native delivery. Keep its
    # issued API key and continuation URL; action codes never enter logs.
    expected = 'verifyEmail' if kind == 'verify' else 'resetPassword'
    if params.get('mode') != [expected] or not params.get('oobCode') or not params.get('apiKey'):
        raise RuntimeError('email_action_configuration_invalid')
    # Verification stays on the hiring origin, where the applicant is signed in.
    # Its handler checks the code's email against the current session before
    # continuing. Password reset retains the existing Google-managed handler.
    handler = base + '/account/action' if kind == 'verify' else 'https://cookcredit.com/__/auth/action'
    return handler + '?' + urlencode({
        key: params[key][0] for key in ('mode', 'oobCode', 'apiKey', 'continueUrl', 'lang') if key in params
    })


from services.mail_transport import send_google_smtp as _send_google_smtp


def deliver_account_email(item):
    if item.kind in ('access_requested', 'access_approved'):
        return deliver_access_email(item)
    delivery_provider = os.environ.get('AUTH_EMAIL_PROVIDER', 'firebase')
    # Native Firebase clients do not use this outbox for verification/reset.
    if item.kind in ('verify', 'reset') and delivery_provider not in ('sendgrid', 'google_smtp'):
        return 'skipped'
    if item.kind == 'welcome' and os.environ.get('AUTH_WELCOME_EMAILS_ENABLED') != '1':
        return 'skipped'
    from services.hiring_access import access_allowed, enabled
    # Public role applicants need account mail before they can apply. Employer
    # approval governs dashboard access, not ownership of an applicant's inbox.
    # Keep the recipient guard for isolated staging without public applicants.
    if deployment_environment() == 'staging' and not enabled():
        if not access_allowed(item.recipient, legacy_setting='AUTH_EMAIL_TEST_RECIPIENTS'):
            return 'skipped'
    provider = get_auth()
    try:
        user = provider.get_user(item.user_id) if item.user_id else provider.get_user_by_email(item.recipient)
    except provider.UserNotFoundError:
        return 'skipped'
    if user.disabled or not user.email or user.email.casefold() != item.recipient.casefold():
        return 'skipped'
    if item.kind == 'verify' and user.email_verified:
        return 'skipped'
    if item.kind == 'welcome' and not user.email_verified:
        return 'skipped'
    link = (os.environ['FRONTEND_URL'].split(',')[0].rstrip('/') + '/login'
            if item.kind == 'welcome' else _action_link(item.kind, user.email))
    subject, plain, markup = account_email_content(item.kind, link)
    send_account_message(user.email, subject, plain, markup)
    return 'sent'


def deliver_access_email(item):
    from services.hiring_access import enabled, OWNER_EMAIL
    from models.hiring_access import HiringAccessRequest
    if not enabled():
        return 'skipped'
    with db_session() as session:
        row = session.get(HiringAccessRequest, item.access_request_id)
        if not row:
            return 'skipped'
        if item.kind == 'access_requested':
            if item.recipient != OWNER_EMAIL or row.status != 'pending':
                return 'skipped'
        elif (row.status != 'approved' or row.revision != item.access_revision
              or row.email != item.recipient):
            return 'skipped'  # Revoked or superseded invitations cannot grant access.
    base = os.environ['FRONTEND_URL'].split(',')[0].rstrip('/')
    path = '/owner/access' if item.kind == 'access_requested' else '/signup?next=/business/onboarding'
    subject, plain, markup = account_email_content(item.kind, base + path)
    send_account_message(item.recipient, subject, plain, markup)
    return 'sent'


def send_account_message(recipient, subject, plain, markup):
    if os.environ.get('AUTH_EMAIL_PROVIDER') == 'google_smtp':
        _send_google_smtp(recipient, subject, plain, markup)
        return
    response = requests.post('https://api.sendgrid.com/v3/mail/send', timeout=(3, 12),
        headers={'Authorization': 'Bearer ' + os.environ['SENDGRID_API_KEY']},
        json={'personalizations': [{'to': [{'email': recipient}]}],
              'from': {'email': os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@cookcredit.com'), 'name': 'CookCredit'},
              'reply_to': {'email': 'connectwithus@cookcredit.com', 'name': 'CookCredit'},
              'subject': subject,
              'content': [{'type': 'text/plain', 'value': plain}, {'type': 'text/html', 'value': markup}],
              'tracking_settings': {'click_tracking': {'enable': False, 'enable_text': False},
                                    'open_tracking': {'enable': False}}}, allow_redirects=False)
    if response.status_code != 202:
        raise RuntimeError('email_provider_unavailable')


def _deliver_safely(item):
    try:
        return item, deliver_account_email(item)
    except Exception:
        # Never return provider exceptions, addresses or action codes to callers.
        return item, 'failed'


def dispatch_account_emails(limit=50):
    # SMTP uses several bounded network operations per message. Keep each
    # batch within the scheduler deadline and well within the ten-minute lease.
    batch_cap = 5 if os.environ.get('AUTH_EMAIL_PROVIDER') == 'google_smtp' else 50
    limit = max(1, min(batch_cap, int(limit)))
    now = utcnow()
    with db_session() as session:
        session.query(AccountEmail).filter(AccountEmail.status == 'sending',
            AccountEmail.attempts >= 8, AccountEmail.lease_until < now).update(
                {'status': 'failed', 'last_error': 'delivery_lease_expired', 'lease_token': None,
                 'lease_until': None}, synchronize_session=False)
        rows = (session.query(AccountEmail).filter(
            AccountEmail.attempts < 8, AccountEmail.available_at <= now,
            or_(AccountEmail.status == 'pending', and_(AccountEmail.status == 'sending', AccountEmail.lease_until < now)))
            .order_by(AccountEmail.available_at).with_for_update(skip_locked=True).limit(limit).all())
        for item in rows:
            item.status = 'sending'; item.attempts += 1
            item.lease_token = uuid.uuid4(); item.lease_until = now + timedelta(minutes=10)
    counts = {'claimed': len(rows), 'sent': 0, 'skipped': 0, 'failed': 0}
    # Network I/O has bounded concurrency and never holds a database connection.
    with ThreadPoolExecutor(max_workers=5) as pool:
        delivered = list(pool.map(_deliver_safely, rows))
    for item, result in delivered:
        with db_session() as session:
            current = session.query(AccountEmail).filter_by(id=item.id, lease_token=item.lease_token).with_for_update().one_or_none()
            if not current:
                continue
            current.lease_until = None; current.lease_token = None
            if result == 'failed':
                current.status = 'failed' if current.attempts >= 8 else 'pending'
                current.available_at = utcnow() + timedelta(seconds=min(3600, 30 * 2 ** current.attempts))
                current.last_error = 'delivery_failed'
            else:
                current.status = result; current.completed_at = utcnow(); current.last_error = None
            counts[result] += 1
    return counts
