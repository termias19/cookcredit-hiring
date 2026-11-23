"""Additional release acceptance faults; fake provider and disposable SQL only."""
from types import SimpleNamespace
import copy,hashlib,hmac,json,time as clock,uuid
import pytest
from datetime import datetime,date,time,timedelta,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select,update,func
from models.home_service import HomeFinancialOperation as Op,HomeStripeEvent,HomeEvent
from services import database,home_mail,home_payments as money,home_finance_worker as worker
from tests.test_home_payments import app,home_db,provider,completed,fresh,detail,change,notify
from tests.test_home_quotes import prepared,activate,rates,offer,approve,post


def test_payment_review_notice_opens_the_operator_queue_not_customer_visits(monkeypatch):
    monkeypatch.setenv('HOME_PUBLIC_URL','https://home.example.test')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','production')
    from services import account_email
    sent=[];monkeypatch.setattr(account_email,'send_account_message',lambda *args:sent.append(args))
    item=SimpleNamespace(recipient=home_mail.SUPPORT,user_id=None,kind='home_notice',
        content={'action':'payment_review_required','bookingId':None})
    assert home_mail.deliver(item)=='sent'
    assert len(sent)==1 and 'https://home.example.test/#team' in sent[0][2]
    assert 'https://home.example.test/#visits' not in sent[0][2]


def test_second_issue_after_reversal_and_re_release_holds_every_outstanding_transfer(app,provider):
    client=app.test_client();row,payment_id,_=completed(client,provider)
    worker.dispatch_operations(provider)
    assert detail(client,row)['payment']['helperFunds']=='transferred_to_stripe'
    assert change(client,fresh(client,row),'report_issue',uid='customer').status_code==200
    worker.dispatch_operations(provider)
    assert detail(client,row)['payment']['helperFunds']=='held_after_reversal'
    assert change(client,fresh(client,row),'resolve_issue',uid='owner').status_code==200
    worker.dispatch_operations(provider)
    assert [kind for kind,_ in provider.calls].count('transfer')==2
    # A second issue must use the latest outstanding transfer rather than assume
    # the immutable operation history contains only one transfer record.
    response=change(client,fresh(client,row),'report_issue',uid='customer')
    assert response.status_code==200,response.json
    worker.dispatch_operations(provider)
    assert detail(client,row)['payment']['helperFunds']=='held_after_reversal'
    assert [kind for kind,_ in provider.calls].count('reverse')==2
    with database.db_session()as session:
        reversals=session.execute(select(Op).where(Op.payment_id==payment_id,Op.kind=='reverse')).scalars().all()
        assert len(reversals)==2 and all(op.status=='succeeded'for op in reversals)


def scheduled_quote(client):
    row=prepared(client);settings=rates();settings['quoteValidMinutes']=10080
    card=activate(client,settings);row=offer(client,row,card)
    row=approve(client,row,uid='helper').json;row=approve(client,row).json
    value=detail(client,row)
    start=datetime.combine(date.fromisoformat(value['date']),time.fromisoformat(value['time']),
        ZoneInfo(value['timeZone'])).astimezone(timezone.utc)
    return row,value['quote'],start


def test_checkout_session_cannot_outlive_the_scheduled_visit_start(app,provider,monkeypatch):
    client=app.test_client();row,quote,start=scheduled_quote(client)
    monkeypatch.setattr(money,'now',lambda:start-timedelta(hours=2))
    result=post(client,f"/visits/{row['id']}/checkout",{'version':row['version'],
        'quoteId':quote['id'],'digest':quote['digest']},'customer')
    assert result.status_code==202,result.json
    with database.db_session()as session:
        operation=session.execute(select(Op).where(Op.kind=='checkout')).scalar_one()
        assert operation.payload['expiresAt']<=int(start.timestamp())
    assert provider.calls==[]


def test_new_checkout_is_refused_when_not_enough_time_remains_before_the_visit(app,provider,monkeypatch):
    client=app.test_client();row,quote,start=scheduled_quote(client)
    monkeypatch.setattr(money,'now',lambda:start-timedelta(minutes=20))
    result=post(client,f"/visits/{row['id']}/checkout",{'version':row['version'],
        'quoteId':quote['id'],'digest':quote['digest']},'customer')
    # Quote issuance already caps the immutable expiry at the appointment.
    # Reuse that guard instead of adding a duplicate payment deadline system.
    assert result.status_code==409 and result.json['code']=='quote_expiring'
    with database.db_session()as session:
        assert session.execute(select(Op).where(Op.kind=='checkout')).first()is None
    assert provider.calls==[]


def transfer_object(operation,provider_id=None):
    return {'id':provider_id or operation.provider_id,'livemode':False,'currency':'usd',
        'amount':operation.payload['amountCents'],'amount_reversed':100,
        'destination':operation.payload['destination'],'source_transaction':operation.payload['chargeId'],
        'transfer_group':'home:'+str(operation.payment_id),
        'metadata':{'cookcredit_product':'home_services','home_payment_id':str(operation.payment_id),
                    'home_operation_id':str(operation.id)}}


def signed_transfer_event(client,obj,event_id=None):
    event={'id':event_id or 'evt_'+uuid.uuid4().hex,'type':'transfer.reversed','livemode':False,'data':{'object':obj}}
    raw=json.dumps(event).encode();stamp=int(clock.time())
    signature=hmac.new(b'synthetic-home-signing-fixture',str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    response=client.post('/api/home/stripe/webhook',data=raw,content_type='application/json',
        headers={'Stripe-Signature':f't={stamp},v1={signature}'})
    assert response.status_code==200,response.json
    return response.json


def test_external_transfer_reversal_is_bound_deduplicated_and_held_without_money_actions(app,provider,monkeypatch):
    client=app.test_client();row,payment_id,checkout_id=completed(client,provider)
    worker.dispatch_operations(provider)
    with database.db_session()as session:
        transfer=session.execute(select(Op).where(Op.payment_id==payment_id,Op.kind=='transfer')).scalar_one()
    obj=transfer_object(transfer);before=fresh(client,row);calls=list(provider.calls)
    # Unrelated Toque events, copied metadata and wrong subject/provider fields
    # must not put a Home payment on hold or enter its durable inbox.
    for field,value in [('id','tr_unrelated'),('destination','acct_other'),('source_transaction','ch_other'),
        ('currency','eur'),('amount',True),('amount_reversed',0),('transfer_group','toque:other'),('livemode',True)]:
        assert signed_transfer_event(client,{**obj,field:value})['ignored']is True
    for field,value in [('cookcredit_product','toque'),('home_payment_id',str(uuid.uuid4())),
        ('home_payment_id',123),('home_operation_id',str(uuid.uuid4())),('home_operation_id',123)]:
        bad=copy.deepcopy(obj);bad['metadata'][field]=value
        assert signed_transfer_event(client,bad)['ignored']is True
    assert signed_transfer_event(client,{**obj,'metadata':['not-a-mapping']})['ignored']is True
    assert fresh(client,row)==before
    with database.db_session()as session:
        assert session.execute(select(func.count(HomeStripeEvent.id)).where(HomeStripeEvent.kind=='transfer.reversed')).scalar_one()==0
    original_payment=provider.payment
    monkeypatch.setattr(provider,'payment',lambda *_:pytest.fail('Checkout is not canonical transfer-reversal evidence'))
    event_id='evt_external_reversal_acceptance'
    assert signed_transfer_event(client,obj,event_id)=={'accepted':True}
    assert signed_transfer_event(client,obj,event_id)=={'accepted':True}
    assert worker.dispatch_events(provider)['processed']==1
    held=detail(client,row)
    assert held['issueOpen'] and held['payment']['status']=='review_required'
    assert held['payment']['helperFunds']=='provider_review_required'
    assert held['payment']['helperTransferredCents']is None and held['payment']['helperTransferBalanceKnown']is False
    assert signed_transfer_event(client,obj)=={'accepted':True}
    assert worker.dispatch_events(provider)['processed']==1
    assert fresh(client,row)['version']==held['version']
    denied=change(client,fresh(client,row),'resolve_issue',uid='owner')
    assert denied.status_code==409 and denied.json['code']=='provider_reconciliation_required'
    assert detail(client,row)['issueOpen']
    monkeypatch.setattr(provider,'payment',original_payment)
    notify(client,provider,checkout_id)
    assert worker.dispatch_events(provider)['processed']==1
    assert detail(client,row)['payment']['status']=='review_required'
    assert worker.dispatch_operations(provider)['processed']==0 and provider.calls==calls
    with database.db_session()as session:
        reviews=session.execute(select(HomeEvent).where(HomeEvent.action=='payment_review_required')).scalars().all()
        assert len(reviews)==1 and reviews[0].details['reason']=='external_transfer_reversal'


def test_known_home_issued_reversal_webhook_does_not_create_an_external_hold(app,provider):
    client=app.test_client();row,payment_id,_=completed(client,provider)
    worker.dispatch_operations(provider)
    assert change(client,fresh(client,row),'report_issue',uid='customer').status_code==200
    worker.dispatch_operations(provider)
    with database.db_session()as session:
        transfer=session.execute(select(Op).where(Op.payment_id==payment_id,Op.kind=='transfer')).scalar_one()
    assert signed_transfer_event(client,transfer_object(transfer))=={'accepted':True}
    assert worker.dispatch_events(provider)['processed']==1
    assert detail(client,row)['payment']['helperFunds']=='held_after_reversal'
    assert change(client,fresh(client,row),'resolve_issue',uid='owner').status_code==200
    worker.dispatch_operations(provider)
    assert detail(client,row)['payment']['helperFunds']=='transferred_to_stripe'


def test_reversal_webhook_before_transfer_apply_is_retried_until_the_binding_is_known(app,provider):
    client=app.test_client();row,payment_id,_=completed(client,provider)
    original=provider.transfer
    def early_webhook(operation_id,payload):
        result=original(operation_id,payload)
        with database.db_session()as session:
            operation=session.get(Op,uuid.UUID(operation_id))
        assert signed_transfer_event(client,transfer_object(operation,result['id']))=={'accepted':True}
        assert worker.dispatch_events(provider)['deferred']==1
        return result
    provider.transfer=early_webhook
    worker.dispatch_operations(provider)
    with database.db_session()as session:
        event=session.execute(select(HomeStripeEvent).where(HomeStripeEvent.kind=='transfer.reversed')).scalar_one()
        assert event.status=='retry' and event.last_error=='transfer_confirmation_pending'
        event.available_at=money.now()-timedelta(seconds=1)
    assert worker.dispatch_events(provider)['processed']==1
    assert detail(client,row)['payment']['helperFunds']=='provider_review_required'
