import os
from concurrent.futures import ThreadPoolExecutor
import pytest
from models.account_email import AccountEmail
from services import account_email, database, email_capacity
from tests.test_report_playback_binding import db

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='isolated PostgreSQL required')

def test_concurrent_admissions_cannot_overfill_and_retries_do_not_take_extra_slots(db, monkeypatch):
    AccountEmail.__table__.create(database.SessionLocal.kw['bind'])
    monkeypatch.setattr(email_capacity, 'MAX_PENDING', 3)
    def enqueue(index):
        try:
            with database.db_session() as session:
                account_email.enqueue_account_email(session, kind='reset', recipient=f'cook-{index}@example.test')
            return True
        except email_capacity.EmailQueueBusy:
            return False
    with ThreadPoolExecutor(max_workers=9) as pool:
        accepted = list(pool.map(enqueue, range(9)))
    assert sum(accepted) == 3
    winner = accepted.index(True)
    assert enqueue(winner)
    with database.db_session() as session:
        assert session.query(AccountEmail).count() == 3
        session.query(AccountEmail).first().status = 'sent'
    assert enqueue(10)
    with database.db_session() as session:
        assert session.query(AccountEmail).filter(AccountEmail.status.in_(('pending','sending'))).count() == 3
