"""Home durable-health summaries with fake sessions only; no database/provider."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from flask import Flask
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from services import operations

STAMP=datetime(2026,10,31,20,0,tzinfo=timezone.utc)


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return STAMP


class Query:
    def __init__(self,session,columns):
        self.session=session;self.statement=select(*columns)
    def filter(self,*predicates):
        self.statement=self.statement.where(*predicates);return self
    def one(self):
        self.session.statements.append(self.statement)
        return self.session.result
    def scalar(self):
        self.session.statements.append(self.statement)
        return 0


@pytest.fixture
def observation(monkeypatch):
    session=SimpleNamespace(result=(0,0,None,0,0,0,None,0),statements=[])
    session.query=lambda *columns:Query(session,columns)
    @contextmanager
    def fake_session():yield session
    monkeypatch.setattr(operations,'db_session',fake_session)
    monkeypatch.setattr(operations,'datetime',Clock)
    events=[];monkeypatch.setattr(operations,'emit_event',lambda name,**fields:events.append((name,fields)))
    return session,events


@pytest.mark.parametrize('kind',['home_financial','home_events'])
def test_empty_home_queues_are_healthy_and_emit_only_constant_size_summaries(observation,kind):
    session,events=observation
    assert operations.report_queue_health(kind)
    assert len(session.statements)==1 and len(events)==1
    name,event=events[0]
    assert name=='queue_health'and event['severity']=='INFO'and event['queue']==kind
    assert set(event)=={'severity','queue','failed','pending','oldestSeconds','held','expiredLeases',
        'paymentReviews','expectedWaiting','expectedWaitingOldestSeconds','expectedWaitingOverdue'}
    assert not any(word in event for word in ('payload','email','address','token','paymentId','bookingId'))


@pytest.mark.parametrize('kind',['home_financial','home_events'])
@pytest.mark.parametrize('seconds,healthy',[(0,True),(599,True),(600,False),(1800,False)])
def test_stale_actionable_work_alerts_even_when_the_current_batch_processed_nothing(observation,kind,seconds,healthy):
    session,events=observation
    session.result=(0,1,STAMP-timedelta(seconds=seconds),0,0,0,None,0)
    assert operations.report_queue_health(kind)is healthy
    event=events[-1][1]
    assert event['pending']==1 and event['oldestSeconds']==seconds
    assert event['severity']==('INFO'if healthy else'ERROR')


@pytest.mark.parametrize('days,healthy',[(2,True),(6,True),(7,False),(8,False)])
def test_expected_source_funds_wait_has_a_distinct_bounded_escalation_window(observation,days,healthy):
    session,events=observation
    session.result=(0,0,None,0,0,1,STAMP-timedelta(days=days),0)
    assert operations.report_queue_health('home_financial')is healthy
    event=events[-1][1]
    assert event['pending']==0 and event['oldestSeconds']==0
    assert event['expectedWaiting']==1 and event['expectedWaitingOldestSeconds']==days*86400
    assert event['expectedWaitingOverdue']is not healthy


@pytest.mark.parametrize('result,field',[
    ((1,0,None,0,0,0,None,0),'failed'),
    ((0,0,None,1,0,0,None,0),'held'),
    ((0,1,STAMP,0,1,0,None,0),'expiredLeases'),
    ((0,0,None,0,0,0,None,1),'paymentReviews'),
])
def test_terminal_review_holds_abandoned_leases_and_payment_only_holds_are_actionable(observation,result,field):
    session,events=observation;session.result=result
    assert not operations.report_queue_health('home_financial')
    assert events[-1][1]['severity']=='ERROR'and events[-1][1][field]==1


def test_expected_wait_still_alerts_an_abandoned_running_lease(observation):
    session,events=observation
    session.result=(0,0,None,0,1,1,STAMP-timedelta(days=2),0)
    assert not operations.report_queue_health('home_financial')
    assert events[-1][1]['expiredLeases']==1


def test_home_financial_sql_includes_unambiguous_wait_and_review_predicates_without_sensitive_columns(observation):
    session,_=observation
    operations.report_queue_health('home_financial')
    compiled=session.statements[0].compile(dialect=postgresql.dialect())
    sql=str(compiled)
    assert 'mutation_started_at IS NULL'in sql and ') IS true'in sql
    assert 'lease_until IS NULL'in sql and 'lease_until <'in sql
    assert 'home_payments.disputed IS true'in sql and 'home_payments.status ='in sql
    assert 'funds_pending'in compiled.params.values()
    assert 'external_transfer_recovered'in compiled.params.values()
    assert 'home_financial_operations.status IN'in sql
    for private_column in ('payload','actor_id','booking_id','payment_id','provider_id','checkout_url'):
        assert private_column not in sql


def test_home_event_summary_never_counts_payment_reviews_twice_or_requires_operation_only_fields(observation):
    session,_=observation
    operations.report_queue_health('home_events')
    sql=str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert 'home_stripe_events'in sql
    assert 'home_payments'not in sql and 'mutation_started_at'not in sql


@pytest.mark.parametrize('kind',['email','webhook','billing'])
def test_legacy_queue_contracts_keep_their_existing_query_and_log_shape(observation,kind):
    session,events=observation
    session.result=(0,0,None)if kind=='billing'else(0,None)
    assert operations.report_queue_health(kind)
    assert events[-1]==('queue_health',{'severity':'INFO','queue':kind,'failed':0,'pending':0,'oldestSeconds':0})


def test_home_dispatch_observes_financial_state_even_while_payments_are_off(monkeypatch):
    from routes import home_visits
    from services import home_mail,home_dispatch,home_finance_worker,home_stripe,internal_auth
    monkeypatch.setenv('HOME_EMAILS_ENABLED','0')
    monkeypatch.setattr(home_stripe,'mode',lambda:'off')
    monkeypatch.setattr(internal_auth,'internal_request_authorized',lambda request:True)
    no_provider=Mock(side_effect=AssertionError('Paused financial workers must not run'))
    monkeypatch.setattr(home_finance_worker,'dispatch_events',no_provider)
    monkeypatch.setattr(home_finance_worker,'dispatch_operations',no_provider)
    monkeypatch.setattr(home_mail,'convert_events',lambda:{'converted':0})
    calls=[]
    monkeypatch.setattr(operations,'report_queue_health',lambda kind:calls.append(kind)or kind!='home_financial')
    @contextmanager
    def fake_session():yield SimpleNamespace()
    monkeypatch.setattr(home_visits,'db_session',fake_session)
    followup=Mock();monkeypatch.setattr(home_dispatch,'request_next',followup)
    with Flask(__name__).test_request_context('/api/home/internal/dispatch',method='POST'):
        response=home_visits.internal_dispatch()
        assert response.json['healthy']is None
        assert response.json['financialHealthy']is False and response.json['eventsHealthy']is True
        assert response.json['events']=={'paused':True}and response.json['operations']=={'paused':True}
    assert calls==['home_financial','home_events']and not no_provider.called
    followup.assert_called_once()
