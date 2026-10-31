"""Enrollment reuses Home membership and household storage; real disposable SQL."""
import uuid
from sqlalchemy import select,func
from models import Booking
from models.home_service import HomeHousehold,HomeEvent
from models.account_email import AccountEmail
from services import database,home_mail
from tests.test_home_visits import app,home_db,headers
from tests.test_home_quotes import fully_approved

def save(client,uid='customer',key=None,**extra):
    return client.put('/api/home/enrollment',headers=headers(uid,key or uuid.uuid4().hex),
        json={'service':'both','phone':'404 555 0199','contactConsent':True,**extra})

def test_enrollment_is_owner_only_deduplicated_and_does_not_create_a_booking(app,monkeypatch):
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    c=app.test_client();key=uuid.uuid4().hex
    first=save(c,key=key);assert first.status_code==200,first.json
    assert save(c,key=key).json==first.json
    assert save(c).json==first.json # Same needs do not generate another notification.
    assert c.get('/api/home/enrollments').status_code==401
    for uid in ('customer','operator','helper','unverified'):
        assert c.get('/api/home/enrollments',headers=headers(uid)).status_code==403
    rows=c.get('/api/home/enrollments',headers=headers('owner')).json['enrollments']
    assert len(rows)==1 and rows[0]['email']=='customer@example.test'
    assert rows[0]['service']=='both' and rows[0]['phone']=='+14045550199'
    assert c.get('/api/home/enrollment',headers=headers('stranger')).json['enrollment'] is None
    assert c.get('/api/home/household',headers=headers()).json['household'] is None
    home_mail.convert_events()
    with database.db_session() as session:
        assert session.execute(select(func.count(Booking.id))).scalar_one()==0
        assert session.query(HomeHousehold).count()==1
        assert session.query(HomeEvent).filter_by(action='service_interest_saved').count()==1
        messages=session.execute(select(AccountEmail)).scalars().all()
        assert len(messages)==2
        notice=next(m for m in messages if m.content['action']=='service_interest_saved')
        assert notice.recipient==home_mail.SUPPORT
        assert notice.content=={'action':'service_interest_saved','bookingId':None}

def test_enrollment_and_saved_household_preserve_each_other_and_withdrawal_clears_contact(app):
    c=app.test_client();saved={'address':'Synthetic saved address','instructions':{'preferences':['allergies'],
        'cleaningTasks':['kitchen'],'visitNotes':'PRIVATE_SYNTHETIC_NOTE'},'remember':True}
    assert c.put('/api/home/household',json=saved,headers=headers(key=uuid.uuid4().hex)).status_code==200
    assert save(c).status_code==200
    assert c.get('/api/home/household',headers=headers()).json['household']['instructions']==saved['instructions']
    assert c.put('/api/home/household',json=saved,headers=headers(key=uuid.uuid4().hex)).status_code==200
    assert c.get('/api/home/enrollment',headers=headers()).json['enrollment']['service']=='both'
    directory=c.get('/api/home/enrollments',headers=headers('owner'))
    assert 'PRIVATE_SYNTHETIC_NOTE' not in directory.get_data(as_text=True)
    assert 'Synthetic saved address' not in directory.get_data(as_text=True)
    assert c.delete('/api/home/household',json={},headers=headers(key=uuid.uuid4().hex)).status_code==200
    assert c.get('/api/home/enrollment',headers=headers()).json['enrollment']['service']=='both'
    key=uuid.uuid4().hex
    for _ in range(2):assert c.delete('/api/home/enrollment',json={},headers=headers(key=key)).status_code==200
    row=c.get('/api/home/enrollments',headers=headers('owner')).json['enrollments'][0]
    assert row['withdrawn'] and row['phone'] is None and row['service'] is None
    assert save(c,service='cooking',phone='').status_code==200
    assert not c.get('/api/home/enrollments',headers=headers('owner')).json['enrollments'][0]['withdrawn']

def test_enrollment_validates_contact_permission_and_identity(app):
    c=app.test_client()
    for changes in ({'contactConsent':False},{'service':'admin'},{'phone':'not a phone'},{'userId':'owner'}, {'phone':True}):
        assert save(c,**changes).status_code==400
    assert save(c,uid='unverified').status_code==403
    assert save(c,service='not_sure',phone='').status_code==200
    assert c.get('/api/home/enrollments?cursor=invalid%7Ccursor',headers=headers('owner')).status_code==400

def test_enrollment_directory_paginates_without_missing_or_duplicate_members(app):
    c=app.test_client()
    for i in range(53):
        assert c.get('/api/home/me',headers=headers(f'member{i:03}')).status_code==200
    first=c.get('/api/home/enrollments',headers=headers('owner')).json
    second=c.get('/api/home/enrollments?cursor='+first['nextCursor'],headers=headers('owner')).json
    ids=[row['id'] for row in first['enrollments']+second['enrollments']]
    assert len(ids)==len(set(ids))==53 and second['nextCursor'] is None


def test_assignment_notifies_the_helper_through_the_existing_private_outbox(app,monkeypatch):
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    c=app.test_client();row,_=fully_approved(c)
    home_mail.convert_events()
    with database.db_session() as session:
        notice=session.execute(select(AccountEmail).where(AccountEmail.content['action'].astext=='assign')).scalar_one()
        assert notice.recipient=='helper@example.test' and notice.user_id=='helper'
        assert notice.content=={'action':'assign','bookingId':row['id']}


def test_superseded_assignment_never_notifies_a_different_helper(app):
    from sqlalchemy import update
    c=app.test_client();row,_=fully_approved(c)
    with database.db_session() as session:
        event=session.execute(select(HomeEvent).where(HomeEvent.booking_id==uuid.UUID(row['id']),HomeEvent.action=='assign')).scalar_one()
        # A change to no helper also makes the historic assignment obsolete.
        session.execute(update(Booking).where(Booking.id==uuid.UUID(row['id'])).values(cook_id=None))
        assert home_mail._recipients(session,event)==[]
