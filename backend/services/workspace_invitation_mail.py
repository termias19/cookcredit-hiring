"""Workspace invitations use the existing leased mail queue and provider."""
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from models import OrgInvitation
from models.account_email import AccountEmail
from services.database import db_session
from services.email_capacity import reserve_email_slot
from services.partner_integrations import encrypt_webhook_secret, decrypt_webhook_secret


def enqueue_invitation(session, invitation, token):
    key = hashlib.sha256(f'workspace_invite:{invitation.id}'.encode()).hexdigest()
    if not reserve_email_slot(session, key):
        return
    ciphertext = encrypt_webhook_secret(token)
    session.execute(insert(AccountEmail).values(
        id=uuid.uuid4(), dedupe_key=key, kind='workspace_invite',
        recipient=invitation.invited_email, invitation_id=invitation.id,
        invitation_token_ciphertext=ciphertext, status='pending', attempts=0,
        available_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc)
    ).on_conflict_do_nothing(index_elements=['dedupe_key']))


def deliver_invitation(item):
    from services.account_email import account_email_content, send_account_message
    from services.runtime_config import deployment_environment
    if deployment_environment() == 'staging':
        allowed = {email.strip().casefold() for email in os.environ.get('AUTH_EMAIL_TEST_RECIPIENTS', '').split(',') if email.strip()}
        if item.recipient.casefold() not in allowed:
            return 'skipped'
    if not item.invitation_token_ciphertext:
        return 'skipped'
    with db_session() as session:
        invitation = session.get(OrgInvitation, item.invitation_id)
        if (not invitation or invitation.status != 'pending'
                or invitation.expires_at <= datetime.now(timezone.utc)
                or invitation.invited_email != item.recipient):
            return 'skipped'
        expected_hash = invitation.token_hash
    token = decrypt_webhook_secret(item.invitation_token_ciphertext)
    if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected_hash):
        return 'skipped'
    base = os.environ['FRONTEND_URL'].split(',')[0].rstrip('/')
    subject, plain, markup = account_email_content('workspace_invite', base + '/business/invite/' + token)
    # Provider network I/O is outside the database transaction.
    send_account_message(item.recipient, subject, plain, markup)
    return 'sent'
