"""Actual SQL/API tests in disposable Home schemas; no provider or cloud I/O."""
import uuid
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,func
from models import User,Booking
from models.home_service import HomeCallback,HomeCustomerFollowup,HomeAccessAudit,HomeHousehold
from services import database
from tests.test_home_visits import app,home_db,headers,create

ROOT='/api/home'


def enroll(client,uid='customer',name='Jordan Smith'):
    result=client.put(ROOT+'/enrollment',json={'service':'both','phone':'404 555 0199','name':name,'contactConsent':True},
        headers=headers(uid,uuid.uuid4().hex))
    assert result.status_code==200,result.json


def search(client,scope='needs',**body):
    response=client.post(ROOT+'/enrollments/search',json={'scope':scope,**body},headers=headers('owner'))
    assert response.status_code==200,response.json
    return response.json


def call(client,uid=None,name='Jordan Smith',phone='4045550199'):
    body={'requestId':str(uuid.uuid4()),'name':name,'phone':phone,'preferredTime':'Afternoons','contactConsent':True}
    result=client.post(ROOT+'/callbacks',json=body,headers=headers(uid)if uid else{})
    assert result.status_code==202,result.json
    return result.json


def follow(client,row,status,key=None):
    return client.post(ROOT+'/enrollments/'+row['customerId']+'/follow-up',headers=headers('owner',key or uuid.uuid4().hex),
        json={'version':row['version'],'activityAt':row['activityAt'],'status':status})


def callback_action(client,row,action,**body):
    return client.post(ROOT+'/callbacks/'+row['callback']['id']+'/follow-up',headers=headers('owner',uuid.uuid4().hex),
        json={'action':action,'groupVersion':row['callback']['groupVersion'],**body})


def test_one_named_person_with_enrollment_visits_and_signed_in_calls(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    client=app.test_client();enroll(client)
    assert create(client).status_code==201
    call(client,'customer');call(client,'customer')
    rows=search(client)['people']
    assert len(rows)==1
    person=rows[0]
    assert person['name']=='Jordan Smith'and person['customerId']=='customer'
    assert person['visitCount']==1 and person['callbackCount']==2 and person['service']=='both'
    assert 'address'not in person and 'instructions'not in person
    assert 'Synthetic home address'not in str(person)
    with database.db_session()as session:
        assert session.query(User).filter_by(id='customer').count()==1
        assert session.query(Booking.id).count()==1


def test_default_hides_account_only_and_withdrawn_interest_but_all_preserves_them(app):
    client=app.test_client()
    assert client.get(ROOT+'/me',headers=headers('accountonly')).status_code==200
    enroll(client)
    assert len(search(client)['people'])==1
    assert search(client,'accounts')['people'][0]['customerId']=='accountonly'
    assert client.delete(ROOT+'/enrollment',json={},headers=headers('customer',uuid.uuid4().hex)).status_code==200
    assert not search(client)['people']
    people=search(client,'all')['people']
    assert len(people)==2 and next(p for p in people if p['customerId']=='customer')['withdrawn']


def test_anonymous_repeats_group_without_merging_people_who_share_a_phone(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    client=app.test_client()
    call(client,name='Jordan  Smith');call(client,name=' jordan smith ')
    call(client,name='Someone Else')
    people=search(client)['people']
    assert len(people)==2
    group=next(p for p in people if p['callbackCount']==2)
    assert group['kind']=='callback'and group['email']is None
    assert callback_action(client,group,'contacting').status_code==200
    assert callback_action(client,group,'closed').status_code==409
    group=next(p for p in search(client)['people']if p['callbackCount']==2)
    assert callback_action(client,group,'closed').status_code==200
    assert len(search(client)['people'])==1
    assert len(search(client,'all')['people'])==2
    with database.db_session()as session:assert session.query(HomeCallback).count()==3


def test_owner_confirmed_link_and_unlink_preserve_accounts_requests_and_customer_privacy(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    client=app.test_client();enroll(client);call(client);call(client)
    people=search(client)['people'];assert len(people)==2
    unlinked=next(p for p in people if p['kind']=='callback')
    assert callback_action(client,unlinked,'link',customerId='customer').status_code==400
    assert callback_action(client,unlinked,'link',customerId='customer',confirmedSamePerson=True).status_code==200
    people=search(client)['people'];assert len(people)==1 and people[0]['callbackCount']==2
    assert client.get(ROOT+'/callbacks',headers=headers('customer')).status_code==403
    assert callback_action(client,people[0],'unlink').status_code==200
    assert len(search(client)['people'])==2
    with database.db_session()as session:
        assert session.query(HomeCallback).count()==2
        assert session.query(HomeHousehold).count()==1


def test_followup_is_idempotent_done_closes_calls_and_new_activity_reopens_it(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    client=app.test_client();enroll(client);call(client,'customer')
    row=search(client)['people'][0];key=uuid.uuid4().hex
    first=follow(client,row,'done',key);assert first.status_code==200,first.json
    assert follow(client,row,'done',key).json==first.json
    assert not search(client)['people']
    with database.db_session()as session:
        assert session.query(HomeCustomerFollowup).count()==1
        assert session.query(HomeCallback).one().status=='closed'
        assert session.query(HomeAccessAudit).filter_by(action='customer_followup_done').count()==1
    call(client,'customer')
    reopened=search(client)['people'][0]
    assert reopened['status']=='new'and reopened['callbackCount']==1
    assert follow(client,row,'done').status_code==409


def test_only_owner_can_read_link_or_update_and_search_literals_do_not_become_sql(app):
    client=app.test_client();enroll(client)
    for actor in (None,'customer','helper','operator','unverified'):
        h=headers(actor)if actor else{}
        for path in ('/enrollments/search','/enrollments/customer/follow-up','/callbacks/'+str(uuid.uuid4())+'/follow-up'):
            result=client.post(ROOT+path,json={},headers=h)
            assert result.status_code==(401 if actor is None else 403)
    assert not search(client,'all',query="%' OR 1=1 --")['people']
    assert not search(client,'all',query='%')['people']
    assert search(client,query='Jordan')['people'][0]['name']=='Jordan Smith'


def test_keyset_pages_and_search_changes_do_not_duplicate_customers(app):
    from sqlalchemy.dialects.postgresql import insert
    from models.home_service import HomeEvent
    with database.db_session()as session:
        now=datetime.now(timezone.utc)
        for i in range(53):
            uid=f'member{i:03}'
            session.execute(insert(User).values(id=uid,name=f'Member {i}',email=f'{uid}@example.test',created_at=now+timedelta(seconds=i)))
            session.add(HomeEvent(actor_id=uid,action='home_account_created',details={}))
    client=app.test_client();page=search(client,'all')
    more=search(client,'all',cursor=page['nextCursor'])
    ids=[p['id']for p in page['people']+more['people']]
    assert len(ids)==len(set(ids))==53 and more['nextCursor']is None
    changed=client.post(ROOT+'/enrollments/search',json={'scope':'all','query':'Member','cursor':page['nextCursor']},headers=headers('owner'))
    assert changed.status_code==400


def test_owner_can_record_a_missing_name_without_changing_the_login_and_customer_name_wins(app):
    client=app.test_client()
    result=client.put(ROOT+'/enrollment',json={'service':'cooking','phone':'','contactConsent':True},headers=headers('customer',uuid.uuid4().hex))
    assert result.status_code==200
    row=search(client)['people'][0];assert row['nameMissing']and row['nameSource']=='missing'
    response=client.post(ROOT+'/enrollments/customer/follow-up',headers=headers('owner',uuid.uuid4().hex),json={
        'status':row['status'],'version':row['version'],'activityAt':row['activityAt'],'name':'Confirmed Customer Name'})
    assert response.status_code==200,response.json
    assert client.get(ROOT+'/me',headers=headers('customer')).status_code==200
    row=search(client)['people'][0];assert row['name']=='Confirmed Customer Name'and row['nameSource']=='owner'
    with database.db_session()as session:
        assert session.get(User,'customer').email=='customer@example.test'
        assert session.get(User,'customer').name=='customer@example.test'
    enroll(client,name='Customer Provided Name')
    assert search(client)['people'][0]['name']=='Customer Provided Name'


def test_new_call_during_owner_review_cannot_be_closed_using_an_old_group(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    client=app.test_client();call(client)
    row=search(client)['people'][0]
    call(client)
    assert callback_action(client,row,'closed').status_code==409
    assert search(client)['people'][0]['callbackCount']==2


def test_linking_an_older_open_call_reopens_finished_customer_followup(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    client=app.test_client();enroll(client);call(client)
    people=search(client)['people'];customer=next(p for p in people if p['kind']=='customer')
    anonymous=next(p for p in people if p['kind']=='callback')
    assert follow(client,customer,'done').status_code==200
    assert callback_action(client,anonymous,'link',customerId='customer',confirmedSamePerson=True).status_code==200
    row=search(client)['people'][0]
    assert row['customerId']=='customer'and row['status']=='new'and row['callbackCount']==1
    assert follow(client,customer,'done').status_code==409
