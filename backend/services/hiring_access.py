"""Owner decisions grant access; incoming messages only create pending requests."""
import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from models.hiring_access import HiringAccessRequest, HiringAccessEvent
from models.account_email import AccountEmail
from services.database import db_session

OWNER_EMAIL = 'eassefa@cookcredit.com'


def enabled():
    return os.environ.get('HIRING_ACCESS_APPROVALS_ENABLED') == '1'


def normalize_email(value):
    if not isinstance(value, str):
        raise ValueError('Enter a valid email address.')
    value = value.strip().casefold()
    if (len(value) > 254 or not re.fullmatch(r'[^\s@<>;,]+@[^\s@<>;,]+\.[^\s@<>;,]+', value)
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise ValueError('Enter a valid email address.')
    return value


def is_owner(email, verified=True):
    return verified is True and str(email or '').strip().casefold() == OWNER_EMAIL


def access_allowed(email, *, legacy_setting='STAGING_ALLOWED_EMAILS', session=None):
    email = str(email or '').strip().casefold()
    legacy = {x.strip().casefold() for x in os.getenv(legacy_setting, '').split(',') if x.strip()}
    if not enabled():
        return email in legacy
    if email == OWNER_EMAIL:
        return True  # Privileged operations separately require a verified owner token.
    def resolve(session):
        row = session.query(HiringAccessRequest).filter_by(email=email).one_or_none()
        # Anonymous requests must never revoke an existing tester's access.
        # Only an explicit owner decision overrides a legacy tester entry.
        if row and row.status != 'pending':
            return row.status == 'approved'
        return email in legacy
    if session is not None:
        return resolve(session)
    with db_session() as session:
        return resolve(session)


def access_blocked(session, email):
    """An explicit platform denial overrides invitations and workspace membership."""
    row = session.query(HiringAccessRequest).filter_by(email=str(email or '').strip().casefold()).one_or_none()
    return bool(row and row.status in ('declined', 'revoked'))


def workspace_access_allowed(session, org):
    """Use the original employer approval; invited admins cannot approve a company."""
    from models import User
    creator = session.get(User, org.created_by) if org.created_by else None
    return bool(creator and access_allowed(creator.email, session=session))


def employer_access_allowed(email, user_id):
    """Resolve current membership on every request so removal takes effect immediately.

    A seat grants access to its approved workspace, not independent employer approval.
    Existing route-level tenant and permission checks remain mandatory.
    """
    if str(email or "").strip().casefold() == OWNER_EMAIL:
        return True  # Verified owner routes retain platform administration access.
    if not enabled():
        return access_allowed(email)
    from models import Org, OrgMembership
    with db_session() as session:
        if access_blocked(session, email):
            return False
        membership = session.query(OrgMembership).filter_by(user_id=user_id).first()
        if membership:
            org = session.get(Org, membership.org_id)
            return bool(org and workspace_access_allowed(session, org))
        return access_allowed(email, session=session)


def enqueue_access_mail(session, row, kind):
    recipient = OWNER_EMAIL if kind == 'access_requested' else row.email
    key = hashlib.sha256(f'{kind}:{row.id}:{row.revision}'.encode()).hexdigest()
    from services.email_capacity import reserve_email_slot
    if not reserve_email_slot(session, key):
        return
    session.execute(insert(AccountEmail).values(
        id=uuid.uuid4(), dedupe_key=key, kind=kind, recipient=recipient,
        access_request_id=row.id, access_revision=row.revision,
        status='pending', attempts=0, available_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc)).on_conflict_do_nothing(index_elements=['dedupe_key']))


def create_request(session, data, *, source, actor_id=None):
    email = normalize_email(data.get('email'))
    fields = {}
    for field, limit in [('name', 120), ('company', 160), ('message', 1500)]:
        value = data.get(field, '')
        if not isinstance(value, str) or len(value) > limit or '\x00' in value:
            raise ValueError(f'{field.capitalize()} must be text of at most {limit} characters.')
        fields[field] = value.strip()
    request_id = session.execute(insert(HiringAccessRequest).values(
        id=uuid.uuid4(), email=email, source=source, **fields,
        status='pending', revision=0, created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)).on_conflict_do_nothing(index_elements=['email'])
        .returning(HiringAccessRequest.id)).scalar_one_or_none()
    row = session.query(HiringAccessRequest).filter_by(email=email).one()
    if request_id:
        session.add(HiringAccessEvent(request_id=row.id, actor_id=actor_id, action='requested:'+source))
        if source != 'owner':
            enqueue_access_mail(session, row, 'access_requested')
    # Repeated public requests never overwrite the original details or owner decision.
    return row, request_id is not None


def decide(session, row, *, action, revision, actor_id, send_email):
    if type(revision) is not int or revision != row.revision:
        raise ValueError('This request changed. Refresh it before deciding.')
    if row.email == OWNER_EMAIL:
        raise ValueError('The owner account cannot be changed here.')
    if action not in ('approve', 'decline', 'revoke', 'resend'):
        raise ValueError('Choose a supported access action.')
    if action == 'resend' and row.status != 'approved':
        raise ValueError('Approve access before sending an invitation.')
    if action == 'revoke' and row.status != 'approved':
        raise ValueError('Only approved access can be revoked.')
    if action == 'decline' and row.status == 'approved':
        raise ValueError('Revoke approved access instead.')
    row.status = {'approve': 'approved', 'decline': 'declined', 'revoke': 'revoked'}.get(action, row.status)
    row.revision += 1
    row.updated_at = row.decided_at = datetime.now(timezone.utc)
    row.decided_by = actor_id
    session.add(HiringAccessEvent(request_id=row.id, actor_id=actor_id, action=action))
    if row.status == 'approved' and (send_email or action == 'resend'):
        enqueue_access_mail(session, row, 'access_approved')
