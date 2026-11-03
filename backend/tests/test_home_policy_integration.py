"""Canonical request/assignment enforcement; suggestions never authorize work."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from tests.test_home_visits import app,home_db,headers,payload,create,seed_helper,change
from tests.test_home_slots import settings,save,activate
from tests.test_home_scheduling import requested,assign


def nearby_start():
    base=datetime.now(timezone.utc)
    value=(base+timedelta(hours=8)).astimezone(ZoneInfo('America/New_York')).replace(minute=0,second=0,microsecond=0)
    if value.replace(fold=0).utcoffset()!=value.replace(fold=1).utcoffset():
        value=(base+timedelta(hours=10)).astimezone(ZoneInfo('America/New_York')).replace(minute=0,second=0,microsecond=0)
    return value


def policy(c,**options):
    assert save(c,settings(**options)).status_code==200
    assert activate(c).status_code==200


def test_customer_request_uses_active_hours_and_not_an_unsaved_or_unactivated_draft(app):
    c=app.test_client();policy(c,start=600,end=1080)
    assert create(c).status_code==201
    denied=create(c,{**payload(),'time':'09:00'})
    assert denied.status_code==409 and denied.json['code']=='outside_operating_hours'
    assert save(c,settings(),1).status_code==200
    assert create(c,{**payload(),'time':'09:00'}).json['code']=='outside_operating_hours'
    assert activate(c,2).status_code==200
    assert create(c,{**payload(),'time':'09:00'}).status_code==201


def test_standard_notice_cannot_be_bypassed_with_a_customer_flag(app):
    c=app.test_client();policy(c)
    soon=nearby_start()
    body={**payload(),'date':soon.date().isoformat(),'time':soon.strftime('%H:%M'),'durationMinutes':60,
        'service':'cooking','instructions':{'preferences':[],'cleaningTasks':[],'visitNotes':''}}
    assert create(c,body).json['code']=='booking_notice_required'
    assert create(c,{**body,'manual':True}).status_code==400


def test_assignment_enforces_full_travel_margin_with_exact_boundary_allowed(app):
    c=app.test_client();seed_helper(c);policy(c,buffer=60)
    assert assign(c,requested(c)).status_code==200  #10:00–12:30
    assert assign(c,requested(c,time='13:00')).json['code']=='helper_schedule_conflict'
    assert assign(c,requested(c,time='13:30')).status_code==200


def test_timezone_change_is_explicit_in_profile_and_stale_form_is_rejected(app):
    c=app.test_client();value={**settings(),'timeZone':'UTC'}
    assert save(c,value).status_code==200 and activate(c).status_code==200
    profile=c.get('/api/home/me',headers=headers()).json
    assert profile['serviceTimeZone']=='UTC' and profile['serviceStates']==['GA']
    denied=create(c,{**payload(),'timeZone':'America/New_York'})
    assert denied.status_code==409 and denied.json['code']=='operating_rules_changed'
    accepted=create(c,{**payload(),'timeZone':'UTC'})
    assert accepted.status_code==201
    detail=c.get('/api/home/visits/'+accepted.json['id'],headers=headers()).json
    assert detail['timeZone']=='UTC'


def test_pre_policy_notice_is_preserved_when_old_manual_request_is_later_assigned(app):
    c=app.test_client();seed_helper(c)
    soon=nearby_start()
    body={**payload(),'date':soon.date().isoformat(),'time':soon.strftime('%H:%M'),'durationMinutes':60,
        'service':'cooking','instructions':{'preferences':[],'cleaningTasks':[],'visitNotes':''}}
    created=create(c,body);assert created.status_code==201
    row=change(c,created.json,'review').json
    policy(c)
    assigned=assign(c,row);assert assigned.status_code==200,assigned.json
    assert change(c,assigned.json,'accept',uid='helper').status_code==200
