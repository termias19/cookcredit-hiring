"""Deployed payment gates and hostile envelopes; no real provider mutations."""
import copy
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
import pytest
from home_app import create_app
from services import home_stripe, home_finance_worker, home_visits


@pytest.fixture
def settings(monkeypatch):
    for key,value in {'HOME_PAYMENT_MODE':'live','HOME_STRIPE_SECRET_KEY':'sk_live_synthetic',
        'HOME_STRIPE_WEBHOOK_SECRET':'whsec_synthetic','HOME_CHECKOUT_ENABLED':'1',
        'HOME_CONNECT_ENABLED':'1','HOME_TRANSFERS_ENABLED':'1','HOME_LIVE_REFUNDS_ENABLED':'1',
        'HOME_PUBLIC_URL':'https://home.example.test'}.items():monkeypatch.setenv(key,value)
    monkeypatch.setattr(home_stripe,'client',lambda:object())


@pytest.mark.parametrize('setting,value',[
    ('HOME_STRIPE_WEBHOOK_SECRET',''),('HOME_STRIPE_WEBHOOK_SECRET','not-a-signing-secret'),
    ('HOME_LIVE_REFUNDS_ENABLED','0'),('HOME_PUBLIC_URL','http://home.example.test'),
    ('HOME_PUBLIC_URL','https://owner:secret@home.example.test'),('HOME_CHECKOUT_ENABLED','yes'),
    ('HOME_PAYMENT_MODE','off'),
])
def test_incomplete_payment_release_fails_before_a_charge_can_be_created(settings,monkeypatch,setting,value):
    monkeypatch.setenv(setting,value)
    with pytest.raises(RuntimeError):home_stripe.validate_configuration()


def test_complete_configuration_performs_no_provider_request_and_exposes_no_credential(settings):
    home_stripe.validate_configuration()
    facts=home_stripe.configuration()
    assert facts=={'mode':'live','checkoutEnabled':True,'webhookConfigured':True,
        'transfersEnabled':True,'refundsEnabled':True,'connectEnabled':True}
    assert 'synthetic'not in json.dumps(facts)


def test_checkout_uses_the_verified_customer_receipt_address_and_namespaced_idempotency(settings,monkeypatch):
    calls=[]
    fake=SimpleNamespace(checkout=SimpleNamespace(sessions=SimpleNamespace(create=lambda params,options:calls.append((params,options))or {'id':'cs_synthetic'})))
    monkeypatch.setattr(home_stripe,'client',lambda:fake)
    payload={'email':'customer@example.test','paymentId':'p','quoteId':'q','attempt':1,'amountCents':12345,
        'expiresAt':1900000000,'bookingId':'b'}
    home_stripe.StripeHome().checkout('operation-one',payload)
    params,options=calls[0]
    assert params['payment_intent_data']['receipt_email']==payload['email']
    assert params['line_items'][0]['price_data']['unit_amount']==12345
    assert params['metadata']['cookcredit_product']=='home_services'
    assert params['branding_settings']['display_name']=='CookCredit Home'
    assert params['branding_settings']['logo']=={'type':'url','url':'https://cookcredit.com/favicon.png'}
    assert options=={'idempotency_key':'home:operation-one'}


EVENT={'id':'evt_synthetic','type':'checkout.session.completed','livemode':True,
    'data':{'object':{'id':'cs_synthetic','metadata':{'cookcredit_product':'another_product'}}}}


@pytest.mark.parametrize('mutation',[
    {'livemode':'true'},{'id':'not-an-event'},{'type':None},{'data':[]},
    {'data':{'object':[]}}, {'data':{'object':{'id':'https://unexpected.example/object'}}},
])
def test_signed_but_malformed_event_cannot_reach_database(settings,mutation):
    with pytest.raises(home_visits.HomeError)as rejected:
        home_finance_worker.receive_event(None,{**copy.deepcopy(EVENT),**mutation})
    assert rejected.value.code=='invalid_event'


def test_other_products_and_unsubscribed_types_are_ignored_without_database_writes(settings):
    assert home_finance_worker.receive_event(None,copy.deepcopy(EVENT))=={'accepted':True,'ignored':True}
    assert home_finance_worker.receive_event(None,{**EVENT,'type':'unsubscribed.event'})=={'accepted':True,'ignored':True}


@pytest.mark.parametrize('age,secret',[(0,'wrong-secret'),(600,'whsec_synthetic')])
def test_forged_and_expired_signatures_fail_before_database(settings,monkeypatch,age,secret):
    monkeypatch.setenv('HOME_ENROLLMENT_ONLY','0')
    app=create_app({'TESTING':True,'HOME_ENABLED':True,'RATELIMIT_ENABLED':False})
    raw=json.dumps(EVENT,separators=(',',':')).encode();stamp=int(time.time())-age
    digest=hmac.new(secret.encode(),str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    response=app.test_client().post('/api/home/stripe/webhook',data=raw,content_type='application/json',
        headers={'Stripe-Signature':f't={stamp},v1={digest}'})
    assert response.status_code==400 and response.json=={'error':'Invalid webhook signature'}
    assert 'noindex'in response.headers['X-Robots-Tag']


def test_owner_pricing_availability_reports_the_current_gate_instead_of_a_preview_constant(settings,monkeypatch):
    from services import home_quotes
    session=SimpleNamespace(get=lambda *args:None,execute=lambda *args:SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[])))
    assert home_quotes.pricing(session)['paymentsAvailable']is True
    monkeypatch.setenv('HOME_CHECKOUT_ENABLED','0')
    assert home_quotes.pricing(session)['paymentsAvailable']is False


def test_production_cannot_accidentally_open_booking_by_omitting_the_scope_flag(monkeypatch):
    monkeypatch.setenv('K_SERVICE','cookcredit-home')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','production')
    monkeypatch.setenv('HOME_SERVICES_ENABLED','1')
    monkeypatch.delenv('HOME_ENROLLMENT_ONLY',raising=False)
    with pytest.raises(RuntimeError,match='explicit enrollment/booking scope'):
        create_app({'TESTING':True})
