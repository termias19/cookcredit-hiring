"""Owner business drafts over existing Home identity, commands and immutable audit."""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func
from models import Booking
from models.home_service import HomeOperatingRules,HomeEvent,HomeAccessAudit
from services import database,home_operating_rules as rules
from tests.test_home_visits import app,home_db,headers


def save(c,body=None,uid='owner',key=None):
    return c.put('/api/home/operating-rules',json=body or {'version':0,'rules':rules.defaults()},
                 headers=headers(uid,key or uuid.uuid4().hex))


def test_draft_is_owner_only_and_default_read_does_not_seed_business_commitments(app):
    c=app.test_client()
    assert c.get('/api/home/operating-rules').status_code==401
    for uid in ('customer','helper','operator','unverified'):
        assert c.get('/api/home/operating-rules',headers=headers(uid)).status_code==403
        assert save(c,uid=uid).status_code==403
    value=c.get('/api/home/operating-rules',headers=headers('owner')).json
    assert value['version']==0 and value['published']is False
    assert value['rules']==rules.defaults() and value['rules']['weeklyHours']==[]
    with database.db_session()as session:
        assert session.execute(select(func.count(HomeOperatingRules.id))).scalar_one()==0
        assert session.execute(select(func.count(Booking.id))).scalar_one()==0


def test_save_replay_and_unchanged_draft_do_not_duplicate_rules_or_notifications(app):
    c=app.test_client();key=uuid.uuid4().hex
    first=save(c,key=key);assert first.status_code==200,first.json
    assert first.json=={'saved':True,'version':1,'published':False}
    assert save(c,key=key).json==first.json
    assert save(c,{'version':1,'rules':rules.defaults()}).json==first.json
    assert save(c).status_code==409
    with database.db_session()as session:
        assert session.execute(select(func.count(HomeOperatingRules.id))).scalar_one()==1
        events=session.execute(select(HomeEvent).where(HomeEvent.action=='operating_rules_draft_saved')).scalars().all()
        assert len(events)==1 and events[0].details['rules']['states']==['GA']
        assert session.execute(select(func.count(HomeAccessAudit.id)).where(HomeAccessAudit.action=='operating_rules_draft_saved')).scalar_one()==1
        assert session.execute(select(func.count(Booking.id))).scalar_one()==0


@pytest.mark.parametrize('field,value',[
    ('states',['ZZ']),('states',[]),('timeZone','Invalid/Zone'),('noticeHours',True),
    ('noticeHours',5),('shortNoticeHours',48),('bufferMinutes',7),
    ('weeklyHours',[{'day':'mon','startMinute':600,'endMinute':540}]),
    ('weeklyHours',[{'day':'mon','startMinute':540,'endMinute':1020}]*2),
])
def test_invalid_rules_are_rejected_without_saving(app,field,value):
    c=app.test_client();settings=rules.defaults();settings[field]=value
    assert save(c,{'version':0,'rules':settings}).status_code==400
    with database.db_session()as session:
        assert session.execute(select(func.count(HomeOperatingRules.id))).scalar_one()==0


def test_valid_hours_are_normalized_and_exact_prior_revisions_remain_in_audit(app):
    c=app.test_client();settings=rules.defaults()
    settings.update(states=['GA','GA','SC'],bufferMinutes=30,weeklyHours=[
        {'day':'sat','startMinute':600,'endMinute':1440}, {'day':'mon','startMinute':540,'endMinute':1020}])
    assert save(c,{'version':0,'rules':settings}).status_code==200
    first=c.get('/api/home/operating-rules',headers=headers('owner')).json
    assert first['rules']['states']==['GA','SC']
    assert [w['day']for w in first['rules']['weeklyHours']]==['mon','sat']
    changed={**first['rules'],'noticeHours':48}
    assert save(c,{'version':1,'rules':changed}).json['version']==2
    with database.db_session()as session:
        events=session.execute(select(HomeEvent).where(HomeEvent.action=='operating_rules_draft_saved').order_by(HomeEvent.created_at)).scalars().all()
        assert [event.details['rules']['noticeHours']for event in events]==[24,48]
    assert c.get('/api/home/operating-rules',headers=headers('owner')).json['published']is False


def test_owner_draft_cannot_bypass_explicit_activation_review(app):
    c=app.test_client()
    assert save(c,{'version':0,'rules':rules.defaults(),'published':True}).status_code==400
    assert c.post('/api/home/operating-rules/activate',json={},headers=headers('owner',uuid.uuid4().hex)).status_code==400


def test_concurrent_owner_tabs_cannot_overwrite_the_same_draft_version(app,monkeypatch):
    c=app.test_client();c.get('/api/home/operating-rules',headers=headers('owner'))
    barrier=threading.Barrier(2);original=rules.save
    def competing(*args):
        barrier.wait(timeout=10)
        return original(*args)
    monkeypatch.setattr(rules,'save',competing)
    def send(notice):
        settings=rules.defaults();settings['noticeHours']=notice
        with app.test_client()as client:
            return save(client,{'version':0,'rules':settings}).status_code
    with ThreadPoolExecutor(max_workers=2)as pool:
        assert sorted(pool.map(send,[24,48]))==[200,409]
    with database.db_session()as session:
        assert session.get(HomeOperatingRules,1).version==1
        assert session.execute(select(func.count(HomeEvent.id)).where(HomeEvent.action=='operating_rules_draft_saved')).scalar_one()==1
