"""Home intake, private evidence and mail acceptance without external effects."""
import io
import uuid
from types import SimpleNamespace
from PIL import Image
import pytest
from sqlalchemy import select,update
from sqlalchemy.exc import DBAPIError
from models.account_email import AccountEmail
from models.home_service import HomeReceipt,HomeEvent,HomeNotificationCursor
from services import database,home_receipts,home_mail
from tests.test_home_quotes import app,home_db,headers,post,fully_approved,detail,reconciliation_body


def photo():
    stream=io.BytesIO();image=Image.new('RGB',(60,40),'white')
    exif=Image.Exif();exif[270]='SYNTHETIC_PRIVATE_METADATA'
    image.save(stream,'JPEG',exif=exif);return stream.getvalue()


def upload(client,row,uid='helper',key=None,data=None):
    return client.post(f"/api/home/visits/{row['id']}/receipts",headers=headers(uid,key or uuid.uuid4().hex),
        data={'file':(io.BytesIO(data or photo()),'receipt.jpg')})


def test_saved_household_is_opt_in_private_and_can_be_removed(app):
    c=app.test_client();body={'address':'Synthetic household','instructions':{'preferences':['allergies'],
        'cleaningTasks':['kitchen'],'visitNotes':'Synthetic private instruction'},'remember':False}
    assert c.put('/api/home/household',json=body,headers=headers(key=uuid.uuid4().hex)).status_code==400
    body['remember']=True
    assert c.put('/api/home/household',json=body,headers=headers(key=uuid.uuid4().hex)).status_code==200
    assert c.get('/api/home/household',headers=headers()).json['household']['address']==body['address']
    assert c.get('/api/home/household',headers=headers('stranger')).json['household'] is None
    assert c.delete('/api/home/household',json={},headers=headers(key=uuid.uuid4().hex)).status_code==200
    assert c.get('/api/home/household',headers=headers()).json['household'] is None


def test_callback_is_durable_idempotent_and_not_publicly_readable(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    c=app.test_client();body={'requestId':str(uuid.uuid4()),'name':'Synthetic Customer','phone':'404 555 0199',
        'preferredTime':'Afternoons','contactConsent':True}
    r=c.post('/api/home/callbacks',json=body);assert r.status_code==202,r.json
    assert c.post('/api/home/callbacks',json=body).json==r.json
    assert c.post('/api/home/callbacks',json={**body,'name':'Different'}).status_code==409
    assert c.get('/api/home/callbacks',headers=headers()).status_code==403
    queue=c.get('/api/home/callbacks',headers=headers('operator')).json['callbacks']
    assert len(queue)==1 and queue[0]['phone']=='+14045550199'


def test_customer_cannot_self_approve_helper_access(app):
    c=app.test_client()
    assert post(c,'/helpers/apply',{'bio':'Synthetic experience','services':'both','contactConsent':True},'customer').status_code==202
    assert not c.get('/api/home/me',headers=headers()).json['helper']
    assert post(c,'/helpers/customer/review',{'enabled':True,'cooking':True,'cleaning':True},'customer').status_code==403
    assert post(c,'/helpers/customer/review',{'enabled':True,'cooking':True,'cleaning':True,'reviewConfirmed':True}).status_code==200
    assert c.get('/api/home/me',headers=headers()).json['helper']


def test_receipt_photo_is_private_stripped_and_immutable(app):
    c=app.test_client();row,_=fully_approved(c);key=uuid.uuid4().hex
    assert upload(c,row,uid='customer').status_code==403
    r=upload(c,row,key=key);assert r.status_code==201,r.json
    evidence=r.json['receipt'];assert upload(c,row,key=key).json==r.json
    path=f"/api/home/visits/{row['id']}/receipts/{evidence['id']}"
    assert c.get(path,headers=headers('stranger')).status_code==404
    result=c.get(path,headers=headers());assert result.status_code==200
    assert 'attachment' in result.headers['Content-Disposition'] and 'no-store' in result.headers['Cache-Control']
    with Image.open(io.BytesIO(result.data))as image:
        assert not image.getexif()
    with pytest.raises(DBAPIError):
        with database.db_session()as session:
            session.execute(update(HomeReceipt).where(HomeReceipt.id==uuid.UUID(evidence['id'])).values(sha256='0'*64))


def test_receipts_cannot_cross_households_and_replay_does_not_need_storage(app):
    c=app.test_client();row,_=fully_approved(c);body=reconciliation_body(c,row)
    invalid={**body,'lines':[{**line,'receiptReference':str(uuid.uuid4())}for line in body['lines']]}
    assert post(c,f"/visits/{row['id']}/materials/reconcile",invalid).json['code']=='receipt_scope'
    from models import Booking
    with database.db_session()as session:
        session.execute(update(Booking).where(Booking.id==uuid.UUID(row['id'])).values(status='completed'))
    key=uuid.uuid4().hex
    result=post(c,f"/visits/{row['id']}/materials/reconcile",body,key=key);assert result.status_code==200,result.json
    home_receipts.get_storage_bucket().objects.clear()
    assert post(c,f"/visits/{row['id']}/materials/reconcile",body,key=key).json==result.json
    assert post(c,f"/visits/{row['id']}/materials/reconcile",{**body,'lines':None}).status_code==400


def test_missing_receipt_generation_fails_closed(app):
    c=app.test_client();row,_=fully_approved(c);body=reconciliation_body(c,row)
    home_receipts.get_storage_bucket().objects.clear()
    assert post(c,f"/visits/{row['id']}/materials/reconcile",body).json['code']=='receipt_unavailable'


def test_welcome_outbox_is_deduplicated_and_contains_no_household_data(app,monkeypatch):
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    from services import home_dispatch
    wakeups=[]
    monkeypatch.setattr(home_dispatch,'enqueue',lambda due:wakeups.append(due))
    c=app.test_client()
    for _ in range(3):assert c.get('/api/home/me',headers=headers()).status_code==200
    assert len(wakeups)==1
    assert home_mail.convert_events()['converted']==1
    assert home_mail.convert_events()['converted']==0
    with database.db_session()as session:
        assert session.query(HomeEvent).filter_by(action='home_account_created').count()==1
        mail=session.execute(select(AccountEmail)).scalar_one()
        assert mail.content=={'action':'home_account_created','bookingId':None}
        assert mail.recipient=='customer@example.test'
        assert session.query(HomeNotificationCursor).filter_by(status='pending').count()==0


def test_home_mail_reuses_the_existing_authenticated_sender(app,monkeypatch):
    monkeypatch.setenv('HOME_PUBLIC_URL','https://home.example.test')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','production')
    monkeypatch.setenv('AUTH_EMAIL_PROVIDER','google_smtp')
    monkeypatch.setenv('GOOGLE_SMTP_USER','owner@cookcredit.com')
    import services.account_email as mail
    sent=[]
    monkeypatch.setattr(mail,'send_account_message',lambda *a:sent.append(a))
    item=SimpleNamespace(recipient=home_mail.SUPPORT,user_id=None,kind='home_notice',content={'action':'callback_requested'})
    assert home_mail.deliver(item)=='sent'
    assert len(sent)==1 and sent[0][0]==home_mail.SUPPORT
    assert home_mail.SUPPORT in sent[0][2]


def test_unverified_account_resend_is_protected_and_has_cooldown(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    c=app.test_client()
    assert c.post('/api/home/account/verification',json={}).status_code==401
    first=c.post('/api/home/account/verification',json={},headers=headers('unverified'))
    assert first.status_code==202 and first.json['queued']
    retry=c.post('/api/home/account/verification',json={},headers=headers('unverified'))
    assert retry.json['queued'] is False and retry.json['retryAfterSeconds']>0


def test_email_return_is_preserved_and_cannot_be_an_external_redirect(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    monkeypatch.setenv('HOME_EMAILS_ENABLED','1')
    c=app.test_client()
    for target in ('https://evil.example','//evil.example','team?next=https://evil.example',{'route':'team'}):
        assert c.post('/api/home/account/verification',json={'returnTo':target},headers=headers('unverified')).status_code==400
    result=c.post('/api/home/account/verification',json={'returnTo':'request'},headers=headers('unverified'))
    assert result.status_code==202
    with database.db_session()as session:
        item=session.execute(select(AccountEmail).where(AccountEmail.kind=='verify')).scalar_one()
        assert item.content=={'homeReturn':'request'}


def test_home_diagnostics_use_the_existing_bounded_private_report_contract(app,monkeypatch):
    monkeypatch.setenv('COOKCREDIT_PRODUCT','home-services')
    monkeypatch.setenv('HOME_FRONTEND_ORIGINS','https://home.example.test')
    c=app.test_client();path='/api/home/observability/client-error'
    report={'code':'render_error','screen':'home_operator','release':'unrecorded','reference':'a'*32}
    assert c.post(path,json=report,headers={'Origin':'https://evil.example'}).status_code==403
    assert c.post(path,json={**report,'message':'private household detail'},headers={'Origin':'https://home.example.test'}).status_code==400
    assert c.post(path,json=report,headers={'Origin':'https://home.example.test'}).status_code==204
