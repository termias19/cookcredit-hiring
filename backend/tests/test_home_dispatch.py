"""No external calls: test coalescing windows and durable follow-up scheduling."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from google.api_core.exceptions import AlreadyExists
from services import database, home_dispatch, webhook_dispatch
from tests.test_home_visits import home_db, app, headers
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


def test_full_outbox_keeps_notice_pending_and_backs_off_without_delaying_account_mail(app,monkeypatch):
    from services import home_mail,email_capacity
    from models.home_service import HomeNotificationCursor
    monkeypatch.setenv('HOME_PAYMENT_MODE','off')
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    wakes=[]
    monkeypatch.setattr(home_dispatch,'enqueue',lambda due:wakes.append(due))
    assert app.test_client().get('/api/home/me',headers=headers('customer')).status_code==200
    def busy(*args,**kwargs):raise email_capacity.EmailQueueBusy('synthetic capacity limit')
    monkeypatch.setattr(email_capacity,'reserve_email_slot',busy)
    assert home_mail.convert_events()=={'converted':0,'backpressured':True}
    later=datetime.now(timezone.utc)+timedelta(seconds=30)
    with database.db_session() as session:
        assert session.query(HomeNotificationCursor).filter_by(status='pending').count()==1
        assert home_dispatch.request_next(session,notifications_not_before=later)==later
    urgent=later-timedelta(seconds=20)
    with database.db_session() as session:
        session.add(AccountEmail(dedupe_key='synthetic-urgent',kind='verify',recipient='synthetic@example.test',available_at=urgent))
    with database.db_session() as session:
        assert home_dispatch.request_next(session,notifications_not_before=later)==urgent
