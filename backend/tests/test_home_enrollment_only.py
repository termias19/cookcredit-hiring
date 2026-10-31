"""Real Flask endpoint gates with fake identity/SQL; no cloud or persistent DB."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import uuid
import pytest
from firebase_admin import app_check
from home_app import create_app
from middleware import auth
from middleware import app_check as app_check_middleware
from services import home_customers as customers,home_visits as visits,home_mail,home_operating_rules as rules
from routes import home_visits,home_customers

VISIT='11111111-1111-4111-8111-111111111111'
QUOTE='22222222-2222-4222-8222-222222222222'
RECEIPT='33333333-3333-4333-8333-333333333333'
BLOCKED=[('GET','/visits'),('POST','/visits'),('GET',f'/visits/{VISIT}'),
    ('POST',f'/visits/{VISIT}/actions'),('GET',f'/visits/{VISIT}/activity'),
    ('PUT','/helpers/helper/permission'),('GET','/pricing'),('POST','/pricing'),
    ('POST',f'/pricing/{QUOTE}/activate'),('POST',f'/visits/{VISIT}/quotes'),
    ('GET',f'/visits/{VISIT}/quotes/{QUOTE}'),('POST',f'/visits/{VISIT}/quotes/{QUOTE}/approve'),
    ('POST',f'/visits/{VISIT}/quotes/{QUOTE}/accept'),('POST',f'/visits/{VISIT}/materials/reconcile'),
    ('POST',f'/visits/{VISIT}/checkout'),('POST',f'/visits/{VISIT}/payment/refresh'),('GET','/operations'),
    ('GET','/operating-rules'),('PUT','/operating-rules'),('POST','/operating-rules/activate'),
    ('GET','/slots'),('GET','/availability'),('PUT','/availability'),('GET','/helpers/helper/availability'),
    ('GET','/household'),('PUT','/household'),('DELETE','/household'),('POST','/helpers/apply'),
    ('GET','/helpers'),('POST','/helpers/helper/review'),('GET','/payout-account'),('POST','/payout-account'),
    ('POST','/payout-account/link'),('GET',f'/visits/{VISIT}/receipts'),
    ('POST',f'/visits/{VISIT}/receipts'),('GET',f'/visits/{VISIT}/receipts/{RECEIPT}')]


def headers(actor='customer',*,attestation=False):
    result={'Authorization':'Bearer '+actor,'Idempotency-Key':uuid.uuid4().hex}
    if attestation:result['X-Firebase-AppCheck']='synthetic-valid-attestation'
    return result


@pytest.fixture
def launch(monkeypatch):
    for key,value in {'HOME_ENROLLMENT_ONLY':'1','HOME_PAYMENT_MODE':'off','HOME_CHECKOUT_ENABLED':'0',
        'HOME_TRANSFERS_ENABLED':'0','HOME_LIVE_REFUNDS_ENABLED':'0','HOME_CONNECT_ENABLED':'0',
        'HOME_OWNER_EMAILS':'owner@example.test','HOME_OPERATOR_EMAILS':'operator@example.test',
        'HOME_ACCEPTANCE_EMAILS':'owner@example.test','HOME_EMAILS_ENABLED':'1',
        'COOKCREDIT_ENVIRONMENT':'production','COOKCREDIT_PRODUCT':'home-services','HOME_FRONTEND_ORIGINS':'https://home.example.test',
        'AUTH_APP_CHECK_REQUIRED':'1','FIREBASE_APP_CHECK_APP_IDS':'home-app'}.items():monkeypatch.setenv(key,value)
    monkeypatch.setattr(auth,'_verify_token',lambda token:{'uid':token,'email':token+'@example.test',
        'name':token,'email_verified':token!='unverified','roles':['owner','helper']})
    monkeypatch.setattr(app_check_middleware,'get_auth',lambda:object())
    def attest(token):
        if token!='synthetic-valid-attestation':raise ValueError('synthetic invalid attestation')
        return {'app_id':'home-app'}
    monkeypatch.setattr(app_check,'verify_token',attest)
    callback=SimpleNamespace(id=uuid.UUID(VISIT),version=0,status='requested')
    session=SimpleNamespace(get=lambda model,key,**kwargs:callback if model.__name__=='HomeCallback'else SimpleNamespace(enabled=True),
        execute=lambda *_:SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[])))
    touched=[]
    @contextmanager
    def fake_sql():touched.append(True);yield session
    monkeypatch.setattr(home_visits,'db_session',fake_sql)
    monkeypatch.setattr(home_customers,'db_session',fake_sql)
    from services import database
    monkeypatch.setattr(database,'db_session',fake_sql)
    import home_app
    monkeypatch.setattr(home_app,'check_home_schema',lambda _:None)
    monkeypatch.setattr(visits,'sync_identity',lambda *_,**__:None)
    monkeypatch.setattr(home_mail,'ensure_welcome',lambda *_:None)
    monkeypatch.setattr(rules,'active',lambda *_,**__:None)
    monkeypatch.setattr(visits,'command',lambda s,actor,key,operation,body,execute:execute())
    monkeypatch.setattr(customers,'enrollment',lambda s,uid:{'service':'cooking','phone':'','ownerId':uid})
    saved=Mock(return_value={'saved':True});withdrawn=Mock(return_value={'removed':True})
    monkeypatch.setattr(customers,'save_enrollment',saved);monkeypatch.setattr(customers,'withdraw_enrollment',withdrawn)
    monkeypatch.setattr(customers,'list_enrollments',lambda *_:{'enrollments':[],'nextCursor':None})
    monkeypatch.setattr(customers,'audit',lambda *_:None)
    callbacks=Mock(return_value={'id':VISIT,'status':'received'});monkeypatch.setattr(customers,'create_callback',callbacks)
    app=create_app({'TESTING':True,'HOME_ENABLED':True,'RATELIMIT_ENABLED':False})
    return SimpleNamespace(app=app,client=app.test_client(),touched=touched,saved=saved,withdrawn=withdrawn,callbacks=callbacks)


@pytest.mark.parametrize('actor',[None,'customer','helper','operator','owner'])
def test_all_visit_household_helper_schedule_and_money_routes_deny_before_any_sql_or_body(launch,actor):
    for method,path in BLOCKED:
        response=launch.client.open('/api/home'+path,method=method,headers=headers(actor)if actor else{},
            data=b'not valid JSON',content_type='application/json')
        assert response.status_code==403,(method,path,response.json)
        assert response.json['code']=='enrollment_only'
        assert response.headers['Cache-Control']=='no-store'and response.headers['X-Request-ID']
    assert not launch.touched


def test_unknown_future_routes_and_disallowed_methods_default_to_denied(launch):
    @launch.app.get('/api/home/new-sensitive-feature')
    def future():pytest.fail('New endpoints require an explicit enrollment-only scope review')
    assert launch.client.get('/api/home/new-sensitive-feature',headers=headers('owner')).json['code']=='enrollment_only'
    assert launch.client.put('/api/home/me',headers=headers('owner')).json['code']=='enrollment_only'
    assert not launch.touched


@pytest.mark.parametrize('actor',['customer','owner','operator','helper'])
def test_me_exposes_authoritative_scope_for_every_identity_without_helper_or_payment_access(launch,actor):
    response=launch.client.get('/api/home/me',headers=headers(actor))
    assert response.status_code==200,response.json
    assert response.json['enrollmentOnly']is True
    assert response.json['paymentsAvailable']is False and response.json['helper']is False
    assert response.json['owner']is(actor=='owner')
    assert response.json['operator']is(actor in ('owner','operator'))


def test_self_enrollment_keeps_verified_identity_and_existing_save_withdraw_controls(launch):
    assert launch.client.get('/api/home/enrollment').status_code==401
    unverified=launch.client.get('/api/home/enrollment',headers=headers('unverified'))
    assert unverified.status_code==403 and unverified.json['code']=='email_unverified'
    response=launch.client.get('/api/home/enrollment',headers=headers())
    assert response.status_code==200 and response.json['enrollment']['ownerId']=='customer'
    assert launch.client.put('/api/home/enrollment',json={'service':'cooking','phone':'','contactConsent':True},headers=headers()).status_code==200
    assert launch.saved.call_args.args[1]['uid']=='customer'
    assert launch.client.delete('/api/home/enrollment',json={},headers=headers()).status_code==200
    assert launch.withdrawn.call_args.args[1]['uid']=='customer'


def test_staff_endpoint_allowlist_never_overrides_existing_exact_roles(launch):
    for path in ('/enrollments','/callbacks','/audit'):
        launch.touched.clear()
        assert launch.client.get('/api/home'+path,headers=headers()).status_code==403
        assert not launch.touched
    assert launch.client.get('/api/home/enrollments',headers=headers('operator')).status_code==403
    assert launch.client.get('/api/home/audit',headers=headers('operator')).status_code==403
    assert launch.client.get('/api/home/enrollments',headers=headers('owner')).status_code==200
    assert launch.client.get('/api/home/audit',headers=headers('owner')).status_code==200
    assert launch.client.get('/api/home/callbacks',headers=headers('operator')).status_code==200
    response=launch.client.post('/api/home/callbacks/'+VISIT,json={'version':0,'status':'closed'},headers=headers('operator'))
    assert response.status_code==200 and response.json=={'updated':True,'version':1}


def test_anonymous_call_requests_keep_real_app_check_and_no_staging_customer_bypass(launch,monkeypatch):
    assert launch.client.post('/api/home/callbacks',json={}).status_code==403
    assert not launch.callbacks.called and not launch.touched
    attestation={'X-Firebase-AppCheck':'synthetic-valid-attestation'}
    response=launch.client.post('/api/home/callbacks',json={'synthetic':True},headers=attestation)
    assert response.status_code==202 and response.json['status']=='received'
    assert launch.callbacks.call_count==1
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','staging')
    assert launch.client.post('/api/home/callbacks',json={},headers=attestation).status_code==401
    blocked=launch.client.get('/api/home/me',headers=headers())
    assert blocked.status_code==403 and blocked.json['code']=='private_acceptance'


def test_verification_reset_and_security_worker_routes_keep_their_existing_guards(launch):
    assert launch.client.post('/api/home/account/verification',json={}).status_code==401
    assert launch.client.post('/api/home/account/reset',json={'email':'customer@example.test'}).status_code==403
    assert launch.client.post('/api/home/internal/dispatch',json={}).status_code==403
    assert launch.client.post('/api/home/stripe/webhook',json={}).status_code==400
    assert not launch.touched


def test_valid_auth_mail_requests_remain_available_with_app_check_and_safe_return(launch,monkeypatch):
    from services import account_email
    queue=Mock(return_value={'queued':True})
    monkeypatch.setattr(account_email,'enqueue_account_email',queue)
    verified=launch.client.post('/api/home/account/verification',json={'returnTo':'enroll'},
        headers=headers('unverified',attestation=True))
    assert verified.status_code==202 and verified.json['queued']is True
    assert queue.call_args.kwargs=={'kind':'verify','recipient':'unverified@example.test',
        'user_id':'unverified','content':{'homeReturn':'enroll'}}
    reset=launch.client.post('/api/home/account/reset',json={'email':'customer@example.test','returnTo':'enroll'},
        headers={'X-Firebase-AppCheck':'synthetic-valid-attestation'})
    assert reset.status_code==202 and reset.json=={'queued':True}
    assert queue.call_args.kwargs=={'kind':'reset','recipient':'customer@example.test','content':{'homeReturn':'enroll'}}


def test_existing_public_error_reporter_remains_available_with_origin_rate_and_code_contract(launch):
    path='/api/home/observability/client-error'
    report={'code':'google_signin_error','screen':'home_customer','release':'a'*40,'reference':'b'*32}
    # Login/security failures must be observable before identity/App Check can
    # succeed. Preserve this reporter's existing strict origin/static-field gate.
    valid=launch.client.post(path,json=report,headers={'Origin':'https://home.example.test'})
    assert valid.status_code==204
    assert launch.client.post(path,json=report,headers={'Origin':'https://unrelated.example'}).status_code==403
    assert launch.client.post(path,json={**report,'rawError':'must not be logged'},
        headers={'Origin':'https://home.example.test'}).status_code==400
    assert not launch.touched


def test_health_is_public_and_cors_origin_policy_is_unchanged(launch):
    response=launch.client.get('/api/home/health',headers={'Origin':'https://home.example.test'})
    assert response.status_code==200 and response.json=={'status':'ok','paymentsAvailable':False,'enrollmentOnly':True}
    assert response.headers['Access-Control-Allow-Origin']=='https://home.example.test'
    rejected=launch.client.options('/api/home/enrollment',headers={'Origin':'https://unrelated.example',
        'Access-Control-Request-Method':'PUT'})
    assert 'Access-Control-Allow-Origin'not in rejected.headers


def test_default_mode_remains_full_private_home_with_existing_auth_gates(launch,monkeypatch):
    monkeypatch.delenv('HOME_ENROLLMENT_ONLY')
    normal=create_app({'TESTING':True,'HOME_ENABLED':True,'RATELIMIT_ENABLED':False})
    assert normal.config['HOME_ENROLLMENT_ONLY']is False
    assert normal.test_client().get('/api/home/visits').status_code==401
    response=normal.test_client().get('/api/home/me',headers=headers())
    assert response.status_code==200 and response.json['enrollmentOnly']is False


@pytest.mark.parametrize('flag',['true','yes',' 1','2'])
def test_malformed_scope_flag_cannot_silently_open_full_home(flag,monkeypatch):
    monkeypatch.setenv('HOME_ENROLLMENT_ONLY',flag)
    with pytest.raises(RuntimeError,match='explicitly 0 or 1'):create_app({'TESTING':True})


@pytest.mark.parametrize('setting,value',[('HOME_PAYMENT_MODE','live'),('HOME_PAYMENT_MODE','test'),
    ('HOME_CHECKOUT_ENABLED','1'),('HOME_TRANSFERS_ENABLED','1'),('HOME_LIVE_REFUNDS_ENABLED','1'),('HOME_CONNECT_ENABLED','1')])
def test_enrollment_only_startup_refuses_any_money_gate(launch,monkeypatch,setting,value):
    monkeypatch.setenv(setting,value)
    with pytest.raises(RuntimeError,match='money gates off'):create_app({'TESTING':True})
