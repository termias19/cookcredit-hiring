"""No external calls: test coalescing windows and durable follow-up scheduling."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from google.api_core.exceptions import AlreadyExists
from services import database, home_dispatch, webhook_dispatch
from tests.test_home_visits import home_db
from models.account_email import AccountEmail


def test_future_coalescing_reuses_pending_wakeup_but_advances_after_it_runs(monkeypatch):
    now = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    calls=[]
    for key,value in {'HOME_TASKS_QUEUE':'projects/example/locations/us-central1/queues/home',
        'HOME_TASKS_TARGET':'https://home.example.test/api/home/internal/dispatch',
        'TASKS_OIDC_AUDIENCE':'https://home.example.test','TASKS_OIDC_SA':'home@example.iam.gserviceaccount.com'}.items():
        monkeypatch.setenv(key,value)
    def create(**kw):
        calls.append(kw['request']['task'])
        if len(calls)==2:raise AlreadyExists('same pending window')
    monkeypatch.setattr(webhook_dispatch,'_client',lambda:SimpleNamespace(create_task=create))
    monkeypatch.setattr(home_dispatch,'_utcnow',lambda:now)
    assert home_dispatch.enqueue(now) and home_dispatch.enqueue(now)
    assert calls[0]['name']==calls[1]['name']
    assert calls[0]['schedule_time'].ToDatetime(tzinfo=timezone.utc)==now+timedelta(seconds=2)
    monkeypatch.setattr(home_dispatch,'_utcnow',lambda:now+timedelta(seconds=3))
    assert home_dispatch.enqueue(now)
    assert calls[-1]['name']!=calls[0]['name']


def test_remaining_mail_schedules_one_followup_and_sent_mail_does_not(home_db,monkeypatch):
    monkeypatch.setenv('HOME_PAYMENT_MODE','off')
    monkeypatch.setenv('HOME_EMAILS_ENABLED','0')
    due=datetime.now(timezone.utc)+timedelta(seconds=45)
    wakes=[]
    monkeypatch.setattr(home_dispatch,'enqueue',lambda value:wakes.append(value))
    with database.db_session() as session:
        item=AccountEmail(dedupe_key='synthetic-followup',kind='reset',recipient='synthetic@example.test',available_at=due)
        session.add(item)
    with database.db_session() as session:
        assert home_dispatch.request_next(session) is None
    assert wakes==[]
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    with database.db_session() as session:
        assert home_dispatch.request_next(session)==due
    assert wakes==[due]
    with database.db_session() as session:
        session.query(AccountEmail).filter_by(dedupe_key='synthetic-followup').one().status='sent'
    with database.db_session() as session:
        assert home_dispatch.request_next(session) is None
    assert wakes==[due]
