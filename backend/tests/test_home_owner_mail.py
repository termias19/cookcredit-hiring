"""Internal follow-up recipient is separate from the public sender/support."""
from types import SimpleNamespace
from services import home_mail
from tests.test_home_visits import app,home_db,create,payload


def test_operator_notices_use_only_configured_deduplicated_owners(monkeypatch):
    monkeypatch.setenv('HOME_OWNER_EMAILS',' Owner@example.test ,owner@example.test ')
    monkeypatch.setenv('HOME_OPERATOR_EMAILS','other-staff@example.test')
    for action in home_mail.OPERATOR_ACTIONS:
        assert home_mail._recipients(None,SimpleNamespace(action=action))==[('owner@example.test',None)]
    assert home_mail.SUPPORT=='connectwithus@cookcredit.com'


def test_unconfigured_development_owner_keeps_existing_support_fallback(monkeypatch):
    monkeypatch.delenv('HOME_OWNER_EMAILS',raising=False)
    assert home_mail._recipients(None,SimpleNamespace(action='callback_requested'))==[(home_mail.SUPPORT,None)]


def test_owner_alert_delivery_keeps_contact_details_private_and_links_to_callback_queue(monkeypatch):
    from services import account_email
    monkeypatch.setenv('HOME_PUBLIC_URL','https://home.example.test')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','production')
    monkeypatch.setenv('HOME_OWNER_EMAILS','owner@example.test')
    delivered=[]
    monkeypatch.setattr(account_email,'send_account_message',lambda *args:delivered.append(args))
    recipient,_=home_mail._recipients(None,SimpleNamespace(action='callback_requested'))[0]
    item=SimpleNamespace(recipient=recipient,user_id=None,kind='home_notice',content={'action':'callback_requested'})
    assert home_mail.deliver(item)=='sent'
    assert len(delivered)==1 and delivered[0][0]=='owner@example.test'
    assert 'https://home.example.test/#team' in delivered[0][2]
    assert home_mail.SUPPORT in delivered[0][2]


def test_new_visit_notifies_customer_and_owner_once_through_the_same_event(app,monkeypatch):
    from sqlalchemy import select
    from models.account_email import AccountEmail
    from models.home_service import HomeEvent
    from services import database
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    monkeypatch.setenv('HOME_OWNER_EMAILS',' Owner@example.test ,owner@example.test ')
    client=app.test_client();body=payload();key='same-synthetic-visit'
    first=create(client,body,key);assert first.status_code==201,first.json
    assert create(client,body,key).json==first.json
    home_mail.convert_events();assert home_mail.convert_events()['converted']==0
    with database.db_session()as session:
        assert session.query(HomeEvent).filter_by(action='visit_requested').count()==1
        notices=session.execute(select(AccountEmail).where(AccountEmail.content['action'].astext.in_(
            ('visit_requested','visit_requested_review')))).scalars().all()
        assert len(notices)==2
        assert {(row.recipient,row.user_id,row.content['action'])for row in notices}=={
            ('customer@example.test','customer','visit_requested'),
            ('owner@example.test',None,'visit_requested_review')}
        for row in notices:
            assert row.content=={'action':row.content['action'],'bookingId':first.json['id']}
            assert body['address']not in str(row.content)and body['instructions']['visitNotes']not in str(row.content)


def test_customer_who_is_also_owner_receives_one_request_confirmation(app,monkeypatch):
    from models.account_email import AccountEmail
    from services import database
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    monkeypatch.setenv('HOME_OWNER_EMAILS',' CUSTOMER@example.test,customer@example.test ')
    response=create(app.test_client());assert response.status_code==201,response.json
    home_mail.convert_events()
    with database.db_session()as session:
        notices=session.query(AccountEmail).filter_by(kind='home_notice').all()
        assert len(notices)==1
        assert (notices[0].recipient,notices[0].user_id,notices[0].content['action'])==(
            'customer@example.test','customer','visit_requested')


def test_partial_fanout_capacity_keeps_whole_request_notification_pending(app,monkeypatch):
    from models.account_email import AccountEmail
    from models.home_service import HomeNotificationCursor
    from services import database
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    response=create(app.test_client());assert response.status_code==201,response.json
    with database.db_session()as session:
        session.add_all(AccountEmail(dedupe_key='synthetic-filled-'+str(i),kind='home_notice',
            recipient='synthetic@example.test',content={})for i in range(89))
    assert home_mail.convert_events()=={'converted':0,'backpressured':True}
    with database.db_session()as session:
        assert session.query(AccountEmail).count()==89
        assert session.query(HomeNotificationCursor).filter_by(status='pending').count()==1
        session.query(AccountEmail).filter_by(dedupe_key='synthetic-filled-0').one().status='sent'
    assert home_mail.convert_events()=={'converted':1,'backpressured':False}
    with database.db_session()as session:
        assert session.query(AccountEmail).count()==91
        assert session.query(HomeNotificationCursor).filter_by(status='pending').count()==0


def test_visit_owner_review_email_uses_private_visit_link_without_household_details(monkeypatch):
    from services import account_email
    monkeypatch.setenv('HOME_PUBLIC_URL','https://home.example.test')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','production')
    sent=[];monkeypatch.setattr(account_email,'send_account_message',lambda *args:sent.append(args))
    visit='11111111-1111-4111-8111-111111111111'
    item=SimpleNamespace(recipient='owner@example.test',user_id=None,kind='home_notice',
        content={'action':'visit_requested_review','bookingId':visit})
    assert home_mail.deliver(item)=='sent'and len(sent)==1
    assert sent[0][1]=='A Home visit request was received'
    assert 'https://home.example.test/#visit/'+visit in sent[0][2]
    assert home_mail.SUPPORT in sent[0][2]
