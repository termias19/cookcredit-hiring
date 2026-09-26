import os
import time
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url
from services import database

@pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='isolated PostgreSQL required')
def test_runtime_connection_timeouts_bound_lock_contention(monkeypatch):
    url = os.environ['HIRING_TEST_DATABASE_URL']
    parsed = make_url(url)
    assert parsed.host in ('127.0.0.1', 'localhost') and parsed.username == 'cookcredit_test'
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setattr(database, 'engine', None)
    monkeypatch.setattr(database, 'SessionLocal', None)
    database.init_db(); engine = database.engine
    try:
        with engine.connect() as first, engine.connect() as second:
            assert first.execute(text('SHOW statement_timeout')).scalar() == '30s'
            assert first.execute(text('SHOW lock_timeout')).scalar() == '3s'
            assert first.execute(text('SHOW idle_in_transaction_session_timeout')).scalar() == '1min'
            key = uuid.uuid4().int % (2**62)
            first.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
            started = time.monotonic()
            with pytest.raises(OperationalError) as failure:
                second.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
            assert failure.value.orig.pgcode == '55P03'
            assert time.monotonic() - started < 8
            second.rollback(); first.rollback()
            assert second.execute(text('SELECT 1')).scalar() == 1
    finally:
        engine.dispose()
