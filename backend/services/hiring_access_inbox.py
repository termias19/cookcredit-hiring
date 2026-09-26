"""Read hiring-request headers only; never mark messages read, reply, or approve.

Both business inboxes use separate credentials mounted from Secret Manager.
Per-mailbox UID checkpoints and database uniqueness make
retries safe. Message content is untrusted; only owner decisions grant access.
"""
import imaplib
import os
import ssl
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesHeaderParser
from email.utils import getaddresses
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from models.hiring_access import HiringAccessInbox
from services.database import db_session
from services.hiring_access import create_request, enabled, normalize_email, OWNER_EMAIL

CONTACT = 'connectwithus@cookcredit.com'
MAILBOXES = ((CONTACT, 'HIRING_INBOX_CONTACT_APP_PASSWORD'),
            (OWNER_EMAIL, 'HIRING_INBOX_OWNER_APP_PASSWORD'))


def parse_request(headers):
    message = BytesHeaderParser(policy=policy.default).parsebytes(headers)
    recipients = {addr.casefold() for _, addr in getaddresses(message.get_all('To', []) + message.get_all('Cc', []))}
    subject = str(message.get('Subject', ''))
    if not recipients.intersection((CONTACT, OWNER_EMAIL)) or 'hiring' not in subject.casefold():
        return None
    if message.get('Auto-Submitted', 'no').casefold() != 'no':
        return None
    senders = getaddresses(message.get_all('From', []))
    if len(senders) != 1:
        return None
    name, address = senders[0]
    try:
        address = normalize_email(address)
    except ValueError:
        return None
    if address in (OWNER_EMAIL, CONTACT):
        return None
    # Never trust Reply-To as the identity to approve. Preserve only bounded headers.
    return {'email': address, 'name': name[:120], 'company': '',
            'message': ('Email subject: ' + subject)[:1500]}


def sync_hiring_inbox(*, connect=None):
    if not enabled() or os.getenv('HIRING_ACCESS_INBOX_ENABLED') != '1':
        return {'enabled': False, 'imported': 0}
    connect = connect or imaplib.IMAP4_SSL
    results = [_sync_mailbox(address, password_env, connect)
               for address, password_env in MAILBOXES]
    return {'enabled': True, 'imported': sum(r.get('imported', 0) for r in results),
            'failed': any(r.get('failed', False) for r in results), 'mailboxes': results}


def _sync_mailbox(address, password_env, connect):
    mailbox = None
    try:
        # One bounded importer at a time. This dedicated transaction never reads
        # applicant media or shares/changes mailbox contents.
        with db_session() as session:
            if not session.execute(text('SELECT pg_try_advisory_xact_lock(hashtext(:key))'),
                                   {'key': 'cookcredit-hiring-inbox:' + address}).scalar():
                return {'mailbox': address, 'busy': True, 'imported': 0}
            session.execute(insert(HiringAccessInbox).values(id=address, last_uid=0)
                            .on_conflict_do_nothing(index_elements=['id']))
            state = session.get(HiringAccessInbox, address)
            mailbox = connect('imap.gmail.com', 993, ssl_context=ssl.create_default_context(), timeout=10)
            mailbox.login(address, ''.join(os.environ[password_env].split()))
            status, _ = mailbox.select('INBOX', readonly=True)
            if status != 'OK':
                raise RuntimeError('mailbox_unavailable')
            validity = mailbox.response('UIDVALIDITY')[1]
            validity = validity[0].decode('ascii') if validity and validity[0] else None
            if not validity:
                raise RuntimeError('mailbox_identity_unavailable')
            if state.uid_validity != validity:
                state.last_uid = 0
                state.uid_validity = validity
            since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%d-%b-%Y')
            status, result = mailbox.uid('search', None, 'SINCE', since, 'SUBJECT', 'hiring',
                                         'UID', f'{state.last_uid + 1}:*')
            if status != 'OK':
                raise RuntimeError('mailbox_search_failed')
            identifiers = sorted(int(x) for x in (result[0] or b'').split() if int(x) > state.last_uid)[:5]
            imported = 0
            for uid in identifiers:
                status, parts = mailbox.uid('fetch', str(uid), '(BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT AUTO-SUBMITTED)])')
                if status != 'OK':
                    raise RuntimeError('mailbox_read_failed')
                raw = next((p[1] for p in parts if isinstance(p, tuple) and isinstance(p[1], bytes)), None)
                if raw is None:
                    raise RuntimeError('mailbox_read_failed')
                data = parse_request(raw[:32768])
                if data:
                    _, created = create_request(session, data, source='inbox')
                    imported += int(created)
                state.last_uid = uid
            state.checked_at = datetime.now(timezone.utc)
            state.last_error = None
            return {'mailbox': address, 'imported': imported}
    except Exception:
        # No credentials, headers, addresses or provider errors enter logs/responses.
        with db_session() as session:
            session.execute(insert(HiringAccessInbox).values(id=address, last_uid=0,
                last_error='Inbox connection needs attention').on_conflict_do_update(
                    index_elements=['id'], set_={'last_error': 'Inbox connection needs attention'}))
        return {'mailbox': address, 'imported': 0, 'failed': True}
    finally:
        if mailbox:
            try:
                mailbox.logout()
            except Exception:
                pass
