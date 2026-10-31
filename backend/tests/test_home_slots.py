"""Activated operating snapshots and advisory slots over real disposable SQL."""
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func,update,text
from sqlalchemy.orm import sessionmaker
from models import Booking
from models.home_service import HomeOperatingRules,HomeEvent,HomeHelperPermission
from services import database,home_operating_rules as rules
from tests.test_home_visits import app,home_db,headers,seed_helper,payload,change
from tests.test_home_scheduling import requested,assign


def settings(*,buffer=0,start=0,end=1440):
    return {**rules.defaults(),'bufferMinutes':buffer,
        'weeklyHours':[{'day':day,'startMinute':start,'endMinute':end}for day in rules.DAYS]}


def save(c,value=None,version=0):
    return c.put('/api/home/operating-rules',json={'version':version,'rules':value or settings()},
        headers=headers('owner',uuid.uuid4().hex))


def activate(c,version=1,actor='owner',key=None):
    return c.post('/api/home/operating-rules/activate',json={'version':version,'reviewConfirmed':True},
        headers=headers(actor,key or uuid.uuid4().hex))


def slots(c,**overrides):
    values={'date':payload()['date'],'service':'both','durationMinutes':'150',**overrides}
    return c.get('/api/home/slots',query_string=values,headers=headers())


def set_interval(row,start,*,duration=150,**fields):
    local=start.astimezone(ZoneInfo('America/New_York'))
    with database.db_session()as session:
        session.execute(update(Booking).where(Booking.id==uuid.UUID(row['id'])).values(
            scheduled_date=local.date(),scheduled_start_time=local.time().replace(tzinfo=None),
            estimated_duration=duration/60,**fields))


@pytest.mark.parametrize('completed',[False,True])
def test_activation_preserves_recently_ended_travel_before_upcoming_assignment(app,completed):
    c=app.test_client();seed_helper(c)
    first=assign(c,requested(c)).json
    second=assign(c,requested(c,time='15:00')).json
    now=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    set_interval(first,now-timedelta(minutes=155),
        **({'status':'completed','completed_at':now-timedelta(minutes=5)}if completed else {}))
    set_interval(second,now+timedelta(minutes=30))
    assert save(c,settings(buffer=60)).status_code==200
    denied=activate(c)
    assert denied.status_code==409 and denied.json['code']=='operating_rules_existing_visit'
    with database.db_session()as session:
        assert session.get(HomeOperatingRules,1).active_version is None
    assert save(c,settings(buffer=30),1).status_code==200
    assert activate(c,2).status_code==200


@pytest.mark.parametrize('status,buffer,minutes,expected',[
    ('completed',60,30,409),('pending_confirmation',60,30,409),
    ('completed',60,60,200),('completed',0,30,200),('cancelled',60,30,200),
])
def test_recent_physical_finish_controls_travel_without_retaining_old_planned_date(app,status,buffer,minutes,expected):
    c=app.test_client();seed_helper(c)
    first=assign(c,requested(c)).json
    target=requested(c,time='15:00')
    now=datetime.now(timezone.utc).replace(second=0,microsecond=0)
    start=now+timedelta(minutes=30)
    # The old scheduled date deliberately falls outside the ordinary date index
    # window. Only the server finish instant can identify this recent travel.
    set_interval(first,now-timedelta(days=5),status='completed',completed_at=now-timedelta(days=4))
    set_interval(target,start)
    assert save(c,settings(buffer=buffer)).status_code==200 and activate(c).status_code==200
    with database.db_session()as session:
        session.execute(update(Booking).where(Booking.id==uuid.UUID(first['id'])).values(
            status=status,completed_at=start-timedelta(minutes=minutes)))
    result=assign(c,target)
    assert result.status_code==expected,result.json
    if expected==409:assert result.json['code']=='helper_schedule_conflict'


def test_slot_calendar_uses_same_physical_finish_and_exact_travel_boundary(app):
    c=app.test_client();seed_helper(c)
    first=assign(c,requested(c)).json
    now=datetime.now(timezone.utc)
    set_interval(first,now-timedelta(days=5),status='completed',completed_at=now-timedelta(days=4))
    assert save(c,settings(buffer=60,start=600,end=1080)).status_code==200 and activate(c).status_code==200
    # Synthetic future finish exercises advisory-query parity without a clock
    # override or simulated real provider/payment event.
    finish=datetime.fromisoformat(payload()['date']+'T13:00:00').replace(tzinfo=ZoneInfo('America/New_York'))
    with database.db_session()as session:
        session.execute(update(Booking).where(Booking.id==uuid.UUID(first['id'])).values(completed_at=finish))
    clocks=[slot['time']for slot in slots(c).json['slots']]
    assert '13:30'not in clocks and '14:00'in clocks


def test_only_owner_can_explicitly_activate_a_complete_saved_revision(app):
    c=app.test_client()
    assert c.post('/api/home/operating-rules/activate',json={}).status_code==401
    assert c.get('/api/home/slots').status_code==401
    for actor in ('customer','operator','helper','unverified'):
        assert activate(c,actor=actor).status_code==403
    assert slots(c).json['code']=='operating_rules_required'
    assert save(c,rules.defaults()).status_code==200
    assert activate(c).json['code']=='operating_rules_incomplete'
    assert c.get('/api/home/operating-rules',headers=headers('owner')).json['activePolicy']is None
    assert save(c,settings(),1).status_code==200
    assert activate(c).json['code']=='operating_rules_changed'
    assert activate(c,2).status_code==200
    value=c.get('/api/home/operating-rules',headers=headers('owner')).json
    assert value['activePolicy']['version']==2 and value['published']is False


def test_activation_retry_and_draft_edit_preserve_one_immutable_active_snapshot(app):
    c=app.test_client();assert save(c).status_code==200;key=uuid.uuid4().hex
    first=activate(c,key=key);assert first.status_code==200,first.json
    assert first.json=={'activated':True,'version':1,'published':False,'reviewRequired':True}
    assert activate(c,key=key).json==first.json and activate(c).json==first.json
    assert save(c,settings(buffer=60),1).status_code==200
    value=c.get('/api/home/operating-rules',headers=headers('owner')).json
    assert value['version']==2 and value['rules']['bufferMinutes']==60
    assert value['activePolicy']['version']==1 and value['activePolicy']['rules']['bufferMinutes']==0
    with database.db_session()as session:
        events=session.execute(select(HomeEvent).where(HomeEvent.action=='operating_rules_activated')).scalars().all()
        assert len(events)==1 and events[0].details['rules']['bufferMinutes']==0
        assert session.execute(select(func.count(Booking.id))).scalar_one()==0


def test_policy_activation_preserves_assigned_work_and_requires_compatible_buffer(app):
    c=app.test_client();seed_helper(c)
    assert assign(c,requested(c)).status_code==200
    assert assign(c,requested(c,time='13:00')).status_code==200
    assert save(c,settings(buffer=60)).status_code==200
    denied=activate(c)
    assert denied.status_code==409 and denied.json['code']=='operating_rules_existing_visit'
    assert 'Synthetic home address'not in str(denied.json)
    with database.db_session()as session:
        assert session.get(HomeOperatingRules,1).active_version is None
        assert session.execute(select(func.count(Booking.id)).where(Booking.cook_id=='helper')).scalar_one()==2
    assert save(c,settings(buffer=30),1).status_code==200
    assert activate(c,2).status_code==200


def test_slots_apply_hours_notice_helper_capability_and_travel_gap_without_identity_leak(app):
    c=app.test_client();seed_helper(c)
    occupied=assign(c,requested(c));assert occupied.status_code==200
    assert save(c,settings(buffer=60,start=600,end=1080)).status_code==200
    assert activate(c).status_code==200
    response=slots(c);assert response.status_code==200,response.json
    assert response.json['slots']==[{'time':clock,'durationMinutes':150}for clock in ('13:30','14:00','14:30','15:00','15:30')]
    assert response.json['reviewRequired']is True and response.json['reservesTime']is False
    assert response.json['areaReviewRequired']is True and response.json['timeZone']=='America/New_York'
    assert 'helper'not in str(response.json)and 'Synthetic'not in str(response.json)and occupied.json['id']not in str(response.json)
    assert c.get('/api/home/operating-rules',headers=headers()).status_code==403


def test_unconfigured_or_disabled_helper_never_looks_bookable(app):
    c=app.test_client();assert save(c,settings(start=600,end=1080)).status_code==200
    assert activate(c).status_code==200
    assert slots(c).json['slots']==[]
    seed_helper(c,available=False)
    assert slots(c).json['slots']==[]
    # A saved helper's capability must also match cooking and cleaning.
    with database.db_session()as session:
        session.execute(update(HomeHelperPermission).where(HomeHelperPermission.user_id=='helper').values(enabled=False))
    assert slots(c).json['slots']==[]


def test_blocked_dates_and_revoked_helper_capability_remove_suggestions(app):
    c=app.test_client();seed_helper(c);assert save(c,settings(start=600,end=1080)).status_code==200
    assert activate(c).status_code==200
    assert slots(c).json['slots']
    from services import home_availability
    body={'version':1,'timeZone':'America/New_York','weeklyHours':[
        {'day':day,'startHour':0,'endHour':24}for day in home_availability.DAYS], 'blockedDates':[payload()['date']]}
    assert c.put('/api/home/availability',json=body,headers=headers('helper',uuid.uuid4().hex)).status_code==200
    assert slots(c).json['slots']==[]
    body.update(version=2,blockedDates=[])
    assert c.put('/api/home/availability',json=body,headers=headers('helper',uuid.uuid4().hex)).status_code==200
    with database.db_session()as session:
        session.execute(update(HomeHelperPermission).where(HomeHelperPermission.user_id=='helper').values(cleaning=False))
    assert slots(c).json['slots']==[]
    assert slots(c,service='cooking').json['slots']


@pytest.mark.parametrize('values',[
    {'date':'2099-01-01'},{'date':'bad'},{'durationMinutes':'90.0'},
    {'durationMinutes':'59'},{'service':'unknown'},{'extra':'not accepted'},
])
def test_slot_queries_are_strict_and_bounded(app,values):
    c=app.test_client();assert save(c).status_code==200;assert activate(c).status_code==200
    assert slots(c,**values).status_code==400


def test_default_notice_and_state_are_applied_without_same_day_capacity_promises(app):
    c=app.test_client();seed_helper(c);assert save(c).status_code==200;assert activate(c).status_code==200
    today=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('America/New_York')).date().isoformat()
    assert slots(c,date=today).json['slots']==[]
    assert slots(c,state='SC').json['code']=='service_area_review_required'
    with database.db_session()as session:
        policy=rules.active(session)
        start=datetime.now(timezone.utc)+timedelta(hours=8)
        with pytest.raises(Exception)as failure:rules.require_notice(policy,start)
        assert failure.value.code=='booking_notice_required'
        rules.require_notice(policy,start,manual=True)


def test_activation_rejects_unsafe_database_isolation(app,home_db,monkeypatch):
    c=app.test_client();assert save(c).status_code==200
    configured=home_db.execution_options(isolation_level='REPEATABLE READ')
    monkeypatch.setattr(database,'SessionLocal',sessionmaker(bind=configured,expire_on_commit=False))
    denied=activate(c)
    assert denied.status_code==503 and denied.json['code']=='calendar_unavailable'


def test_shared_policy_reader_covers_first_activation_and_commitment_visibility(app,monkeypatch):
    c=app.test_client();seed_helper(c);row=requested(c,time='09:00')
    assert save(c,settings(start=600,end=1080)).status_code==200
    holding=threading.Event();finish=threading.Event()
    def assignment():
        with database.db_session()as session:
            assert session.get(HomeHelperPermission,'helper',with_for_update=True).enabled
            assert rules.active(session,lock=True,required=False)is None
            holding.set();assert finish.wait(timeout=10)
            session.execute(update(Booking).where(Booking.id==uuid.UUID(row['id'])).values(cook_id='helper'))
    with ThreadPoolExecutor(max_workers=1)as pool:
        pending=pool.submit(assignment);assert holding.wait(timeout=10)
        with database.db_session()as session:
            assert session.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended('home-operating-rules',0))")).scalar_one()is False
        finish.set();pending.result(timeout=10)
    denied=activate(c)
    assert denied.status_code==409 and denied.json['code']=='operating_rules_existing_visit'


def test_none_policy_preserves_legacy_manual_path_without_opening_slots():
    begin=datetime.now(timezone.utc);end=begin+timedelta(hours=2)
    rules.require_window(None,begin,end);rules.require_notice(None,begin)
    assert rules.buffer_minutes(None)==0


def test_partial_activation_cannot_be_written_even_through_runtime_sql(app):
    from sqlalchemy.exc import DBAPIError
    c=app.test_client();assert save(c).status_code==200
    with pytest.raises(DBAPIError):
        with database.db_session()as session:
            session.execute(update(HomeOperatingRules).where(HomeOperatingRules.id==1).values(active_version=1))


def test_policy_minute_windows_reuse_elapsed_coverage_at_quarter_hour_boundaries():
    policy={'rules':settings(start=615,end=1095)}
    start=datetime.fromisoformat('2026-11-03T15:15:00+00:00') # 10:15 Eastern.
    assert rules.window_covers(policy,start,start+timedelta(hours=8))
    assert not rules.window_covers(policy,start-timedelta(minutes=1),start+timedelta(hours=1))
    assert not rules.window_covers(policy,start,start)


def test_new_notice_does_not_retroactively_invalidate_an_earlier_request():
    from services.home_visits import HomeError
    now=datetime.now(timezone.utc)
    policy={'rules':settings(),'activatedAt':now.isoformat()}
    soon=now+timedelta(hours=8)
    rules.require_notice(policy,soon,reference_time=now-timedelta(hours=1))
    with pytest.raises(HomeError)as failure:
        rules.require_notice(policy,soon,reference_time=now+timedelta(seconds=1))
    assert failure.value.code=='booking_notice_required'
    rules.require_notice(policy,soon,reference_time=now+timedelta(seconds=1),manual=True)


def test_customer_helper_cannot_generate_suggestions_from_only_their_own_hours(app):
    c=app.test_client();seed_helper(c,uid='customer')
    assert save(c).status_code==200;assert activate(c).status_code==200
    assert slots(c).json['slots']==[]
    seed_helper(c,uid='another-helper')
    assert slots(c).json['slots']
