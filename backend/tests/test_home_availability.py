"""Real SQL availability, authorization and assignment/edit race acceptance."""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timedelta,timezone
import pytest
from sqlalchemy import select,func,update
from models import Booking,CookAvailability,CookBlockedDate
from models.home_service import HomeHelperPermission,HomeEvent,HomeVisit
from services import database,home_availability as schedule,home_visits
from tests.test_home_scheduling import requested as reviewed,assign
from tests.test_home_visits import app,home_db,headers,payload,seed_helper,change


def plan(version=0):
    return {'version':version,'timeZone':'America/New_York',
        'weeklyHours':[{'day':day,'startHour':0,'endHour':24}for day in schedule.DAYS], 'blockedDates':[]}


def save(c,body=None,uid='helper',key=None):
    return c.put('/api/home/availability',json=body or plan(),headers=headers(uid,key or uuid.uuid4().hex))


def requested(c,**fields):
    row=reviewed(c,**fields)
    return c.get('/api/home/visits/'+row['id'],headers=headers('owner')).json


def test_only_approved_helper_can_change_own_hours_and_operator_read_is_scoped(app):
    c=app.test_client()
    assert c.get('/api/home/availability').status_code==401
    for actor in ('customer','owner','operator','unverified'):
        assert c.get('/api/home/availability',headers=headers(actor)).status_code==403
        assert save(c,uid=actor).status_code==403
    seed_helper(c,available=False);seed_helper(c,'other',available=False)
    for actor in ('customer','helper','other'):
        assert c.get('/api/home/helpers/helper/availability',headers=headers(actor)).status_code==403
    assert c.get('/api/home/helpers/helper/availability',headers=headers('owner')).status_code==200
    assert c.get('/api/home/helpers/helper/availability',headers=headers('operator')).status_code==200
    assert c.put('/api/home/helpers/other/availability',json=plan(),headers=headers('helper',uuid.uuid4().hex)).status_code==405
    assert save(c,{**plan(),'helperId':'other'}).status_code==400


def test_no_default_coverage_is_seeded_and_midnight_reuses_the_original_models(app):
    c=app.test_client();seed_helper(c,available=False)
    value=c.get('/api/home/availability',headers=headers('helper')).json
    assert value['version']==0 and value['configured']is False and value['weeklyHours']==[]
    row=requested(c)
    denied=assign(c,row)
    assert denied.status_code==409 and denied.json['code']=='helper_availability_required'
    assert save(c).status_code==200
    assert assign(c,row).status_code==200
    with database.db_session()as session:
        sunday=session.execute(select(CookAvailability).where(CookAvailability.cook_id=='helper',CookAvailability.day_of_week==0)).scalar_one()
        assert sunday.start_hour==0 and sunday.end_hour==24
        assert session.execute(select(func.count(CookBlockedDate.id))).scalar_one()==0


def test_schedule_retries_unchanged_saves_and_stale_edits_are_not_duplicates(app):
    c=app.test_client();seed_helper(c,available=False);key=uuid.uuid4().hex
    first=save(c,key=key);assert first.status_code==200,first.json
    assert save(c,key=key).json==first.json
    assert save(c,plan(1)).json==first.json
    assert save(c).status_code==409
    with database.db_session()as session:
        assert session.execute(select(func.count(CookAvailability.id))).scalar_one()==7
        events=session.execute(select(HomeEvent).where(HomeEvent.action=='helper_availability_saved')).scalars().all()
        assert len(events)==1 and events[0].details=={'scheduleVersion':1,'weeklyWindowCount':7,'blockedDateCount':0}


@pytest.mark.parametrize('field,value',[
    ('version',True),('version',-1),('timeZone','Invalid/Zone'),('weeklyHours',None),
    ('weeklyHours',[{'day':'mon','startHour':9,'endHour':8}]),
    ('weeklyHours',[{'day':'mon','startHour':True,'endHour':17}]),
    ('weeklyHours',[{'day':'mon','startHour':9,'endHour':25}]),
    ('weeklyHours',[{'day':'mon','startHour':9,'endHour':17}]*2),
    ('blockedDates',['not-a-date']),('blockedDates',['2099-01-01']),('blockedDates',{}),
])
def test_invalid_input_does_not_save_or_grant_access(app,field,value):
    c=app.test_client();seed_helper(c,available=False)
    assert save(c,{**plan(),field:value}).status_code==400
    with database.db_session()as session:
        assert session.get(HomeHelperPermission,'helper').availability_version==0
        assert session.execute(select(func.count(CookAvailability.id))).scalar_one()==0


def test_blocked_dates_override_hours_and_an_edit_cannot_break_an_assigned_visit(app):
    c=app.test_client();seed_helper(c,available=False);row=requested(c)
    body={**plan(),'blockedDates':[row['date'],row['date']]}
    assert save(c,body).status_code==200
    assert c.get('/api/home/availability',headers=headers('helper')).json['blockedDates']==[row['date']]
    denied=assign(c,row)
    assert denied.status_code==409 and denied.json['code']=='helper_unavailable'
    assert payload()['address']not in str(denied.json)
    assert save(c,plan(1)).status_code==200
    assert assign(c,row).status_code==200
    rejected=save(c,{**body,'version':2})
    assert rejected.status_code==409 and rejected.json['code']=='availability_existing_visit'
    with database.db_session()as session:
        assert session.get(HomeHelperPermission,'helper').availability_version==2
        assert session.get(HomeVisit,uuid.UUID(row['id'])).version==row['version']+1
    assert change(c,{**row,'version':row['version']+1},'cancel').status_code==200
    assert save(c,{**body,'version':2}).status_code==200


def test_full_visit_must_fit_hours_and_acceptance_rechecks_later_constraints(app):
    c=app.test_client();seed_helper(c,available=False)
    day=date.fromisoformat(payload()['date']);name=schedule.DAYS[(day.weekday()+1)%7]
    assert save(c,{**plan(),'weeklyHours':[{'day':name,'startHour':10,'endHour':13}]}).status_code==200
    valid=requested(c);assert assign(c,valid).status_code==200
    outside=requested(c,time='13:00')
    assert assign(c,outside).json['code']=='helper_unavailable'
    # Legacy/manual data cannot bypass a helper's current unavailability at acceptance.
    with database.db_session()as session:
        session.execute(update(Booking).where(Booking.id==uuid.UUID(outside['id'])).values(cook_id='helper'))
    assert change(c,outside,'accept',uid='helper').json['code']=='helper_unavailable'


def test_cross_midnight_visit_checks_next_day_and_half_open_end(app):
    c=app.test_client();seed_helper(c,available=False)
    row=requested(c,time='23:00',durationMinutes=480)
    following=(date.fromisoformat(row['date'])+timedelta(days=1)).isoformat()
    assert save(c,{**plan(),'blockedDates':[following]}).status_code==200
    assert assign(c,row).json['code']=='helper_unavailable'
    one_hour=requested(c,time='23:00',durationMinutes=60)
    assert assign(c,one_hour).status_code==200


def test_schedule_timezone_uses_instants_instead_of_visit_clock_labels(app):
    c=app.test_client();seed_helper(c,available=False)
    day=date.fromisoformat(payload()['date']);name=schedule.DAYS[(day.weekday()+1)%7]
    # New York 10 AM is earlier than UTC 18–23 throughout its timezone offsets.
    assert save(c,{**plan(),'timeZone':'UTC','weeklyHours':[{'day':name,'startHour':18,'endHour':23}]}).status_code==200
    assert assign(c,requested(c)).json['code']=='helper_unavailable'


@pytest.mark.parametrize('start,end,hours,expected',[
    ('2026-11-01T04:30+00:00','2026-11-01T07:30+00:00',(0,3),True),
    ('2026-11-01T04:30+00:00','2026-11-01T07:30+00:00',(0,2),False),
    ('2027-03-14T06:30+00:00','2027-03-14T07:30+00:00',(1,4),True),
    ('2027-03-14T06:30+00:00','2027-03-14T07:30+00:00',(1,3),False),
])
def test_elapsed_coverage_respects_daylight_saving_transitions(start,end,hours,expected):
    value={**plan(),'weeklyHours':[{'day':'sun','startHour':hours[0],'endHour':hours[1]}]}
    assert schedule.covers(value,datetime.fromisoformat(start),datetime.fromisoformat(end))is expected


def test_schedule_edit_and_assignment_share_one_lock_and_cannot_both_win(app,monkeypatch):
    c=app.test_client();seed_helper(c);row=requested(c)
    barrier=threading.Barrier(2);original_helper=schedule.helper;original_allowed=home_visits.helper_allowed
    def edit_lock(session,uid,*,lock=False):
        if lock:barrier.wait(timeout=10)
        return original_helper(session,uid,lock=lock)
    def assign_lock(session,uid,service,*,lock=False):
        if lock:barrier.wait(timeout=10)
        return original_allowed(session,uid,service,lock=lock)
    monkeypatch.setattr(schedule,'helper',edit_lock);monkeypatch.setattr(home_visits,'helper_allowed',assign_lock)
    def mutate(action):
        with app.test_client()as client:
            if action=='edit':return save(client,{**plan(1),'blockedDates':[row['date']]}).status_code
            return assign(client,row).status_code
    with ThreadPoolExecutor(max_workers=2)as pool:
        assert sorted(pool.map(mutate,['edit','assign']))==[200,409]


def test_two_helper_tabs_cannot_overwrite_one_schedule_revision(app,monkeypatch):
    c=app.test_client();seed_helper(c,available=False)
    barrier=threading.Barrier(2);original=schedule.helper
    def compete(session,uid,*,lock=False):
        if lock:barrier.wait(timeout=10)
        return original(session,uid,lock=lock)
    monkeypatch.setattr(schedule,'helper',compete)
    def send(_):
        with app.test_client()as client:return save(client).status_code
    with ThreadPoolExecutor(max_workers=2)as pool:
        assert sorted(pool.map(send,range(2)))==[200,409]
    with database.db_session()as session:
        assert session.get(HomeHelperPermission,'helper').availability_version==1
        assert session.execute(select(func.count(CookAvailability.id))).scalar_one()==7


def test_schedule_edits_reject_an_isolation_level_that_could_hide_an_assignment(app,home_db,monkeypatch):
    from sqlalchemy.orm import sessionmaker
    c=app.test_client();seed_helper(c,available=False)
    configured=home_db.execution_options(isolation_level='REPEATABLE READ')
    monkeypatch.setattr(database,'SessionLocal',sessionmaker(bind=configured,expire_on_commit=False))
    denied=save(c)
    assert denied.status_code==503 and denied.json['code']=='calendar_unavailable'


def test_overdue_requested_visit_cannot_be_assigned_or_accepted(app):
    c=app.test_client();seed_helper(c);row=requested(c)
    with database.db_session()as session:
        session.execute(update(Booking).where(Booking.id==uuid.UUID(row['id']))
            .values(scheduled_date=(datetime.now(timezone.utc)-timedelta(days=2)).date()))
    assert assign(c,row).json['code']=='visit_time_passed'
    with database.db_session()as session:
        session.execute(update(Booking).where(Booking.id==uuid.UUID(row['id'])).values(cook_id='helper'))
    assert change(c,row,'accept',uid='helper').json['code']=='visit_time_passed'


def test_helper_review_and_assignment_use_the_same_lock_order(app,home_db,monkeypatch):
    from sqlalchemy import event as sql_event
    from models import CookProfile
    c=app.test_client();seed_helper(c);row=requested(c)
    with database.db_session()as session:
        session.execute(update(CookProfile).where(CookProfile.user_id=='helper').values(applied_at=datetime.now(timezone.utc)))
    barrier=threading.Barrier(2);role=threading.local();original=home_visits.set_helper_permission
    def before_profile(conn,cursor,statement,parameters,context,executemany):
        if getattr(role,'value',None)=='assign' and 'cook_profiles.approved' in statement and 'FOR UPDATE' in statement:
            barrier.wait(timeout=10)
    def before_permission(*args,**kwargs):
        barrier.wait(timeout=10)
        return original(*args,**kwargs)
    monkeypatch.setattr(home_visits,'set_helper_permission',before_permission)
    sql_event.listen(home_db,'before_cursor_execute',before_profile)
    def send(action):
        role.value=action
        with app.test_client()as client:
            if action=='assign':return assign(client,row).status_code
            return client.post('/api/home/helpers/helper/review',headers=headers('owner',uuid.uuid4().hex),
                json={'enabled':False,'cooking':False,'cleaning':False,'reviewConfirmed':True}).status_code
    try:
        with ThreadPoolExecutor(max_workers=2)as pool:
            assert list(pool.map(send,['assign','review']))==[200,200]
    finally:sql_event.remove(home_db,'before_cursor_execute',before_profile)
    assert c.get('/api/home/visits/'+row['id'],headers=headers('helper')).status_code==404
