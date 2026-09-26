"""Bound the durable mail backlog across all processes without a new service."""
from sqlalchemy import text
from models.account_email import AccountEmail

MAX_PENDING = 100
LOCK_ID = 73570924394123001

class EmailQueueBusy(Exception):
    pass

def reserve_email_slot(session, dedupe_key):
    # Transaction-scoped lock makes the count/insert atomic across instances.
    # Delivery workers do network I/O outside transactions and may drain freely.
    session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': LOCK_ID})
    if session.query(AccountEmail.id).filter_by(dedupe_key=dedupe_key).first():
        return False
    pending = session.query(AccountEmail.id).filter(AccountEmail.status.in_(('pending', 'sending'))).limit(MAX_PENDING).count()
    if pending >= MAX_PENDING:
        raise EmailQueueBusy('Account mail backlog is full')
    return True
