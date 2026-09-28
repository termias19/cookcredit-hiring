"""Real PostgreSQL tests in a unique, disposable schema on an explicit local database.

No app .env is loaded. Set HIRING_TEST_DATABASE_URL; remote databases are rejected.
"""
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
import pytest
from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from models import (Shortlist, ShortlistMember, User, EaterProfile, CookProfile, Org, OrgAssessmentUsage, OrgMembership, OrgInvitation, RolePosting, PipelineCard, SkillAttempt, SkillAttemptEvent,
                    AssessmentShare, AssessmentAccessLog, HiringApplication, ResumeKeypoints,
                    HiringAssessmentSession, HiringApplicationEvent, StripeEvent,
                    PartnerApiKey, PartnerInvitation, PartnerWebhook, PartnerWebhookDelivery)
from services import database, assessment_media, skill_attempts, scoring_dispatch, partner_integrations
from routes import business, skills, assessment_sharing, hiring, embed, partner, cooks, stripe as stripe_routes
from middleware import auth

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='explicit local test database required')


@pytest.fixture
def db(monkeypatch):
    url = os.environ['HIRING_TEST_DATABASE_URL']
    parsed = make_url(url)
    if parsed.host not in ('127.0.0.1', 'localhost') or parsed.username != 'cookcredit_test':
        pytest.fail('Refusing anything except the dedicated local cookcredit_test database user')
    schema = 'hiring_test_' + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public'})
    try:
        for model in (User, EaterProfile, CookProfile, Org, OrgMembership, RolePosting, PipelineCard, Shortlist, ShortlistMember, SkillAttempt, SkillAttemptEvent, ResumeKeypoints):
            model.__table__.create(engine)
        migration = (Path(__file__).parents[1] / 'migrations/011_hiring_evidence_sharing.sql').read_text()
        with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            conn.exec_driver_sql(migration)
            conn.exec_driver_sql(migration)  # migration re-run must be harmless
            lease_migration = (Path(__file__).parents[1] / 'migrations/012_scoring_work_leases.sql').read_text()
            conn.exec_driver_sql(lease_migration)
            conn.exec_driver_sql(lease_migration)
            # Exercise ALTER from the pre-dispatch schema, not just CREATE IF NOT EXISTS.
            conn.exec_driver_sql('ALTER TABLE skill_attempts DROP COLUMN dispatch_due_at, '
                                 'DROP COLUMN dispatch_token, DROP COLUMN dispatch_failures')
            dispatch_migration = (Path(__file__).parents[1] / 'migrations/013_scoring_dispatch.sql').read_text()
            conn.exec_driver_sql(dispatch_migration)
            conn.exec_driver_sql(dispatch_migration)
            hiring_migration = (Path(__file__).parents[1] / 'migrations/014_hiring_applications.sql').read_text()
            conn.exec_driver_sql(hiring_migration)
            conn.exec_driver_sql(hiring_migration)
            details_migration = (Path(__file__).parents[1] / 'migrations/027_hiring_applicant_details.sql').read_text()
            conn.exec_driver_sql(details_migration)
            conn.exec_driver_sql(details_migration)
            billing_migration = (Path(__file__).parents[1] / 'migrations/015_business_subscriptions.sql').read_text()
            conn.exec_driver_sql(billing_migration)
            conn.exec_driver_sql(billing_migration)
            branding_migration = (Path(__file__).parents[1] / 'migrations/016_business_branding.sql').read_text()
            conn.exec_driver_sql(branding_migration)
            conn.exec_driver_sql(branding_migration)
            partner_migration = (Path(__file__).parents[1] / 'migrations/017_partner_api_webhooks.sql').read_text()
            conn.exec_driver_sql(partner_migration)
            conn.exec_driver_sql(partner_migration)
            invitation_migration = (Path(__file__).parents[1] / 'migrations/018_org_invitations.sql').read_text()
            conn.exec_driver_sql(invitation_migration)
            conn.exec_driver_sql(invitation_migration)
            query_index_migration = (Path(__file__).parents[1] / 'migrations/019_hiring_query_indexes.sql').read_text()
            conn.exec_driver_sql(query_index_migration)
            conn.exec_driver_sql(query_index_migration)
            universal_migration = (Path(__file__).parents[1] / 'migrations/020_universal_assessment_requests.sql').read_text()
            conn.exec_driver_sql(universal_migration)
            conn.exec_driver_sql(universal_migration)
            usage_migration = (Path(__file__).parents[1] / 'migrations/021_integration_subscription_usage.sql').read_text()
            conn.exec_driver_sql(usage_migration)
            conn.exec_driver_sql(usage_migration)
            isolation_migration = (Path(__file__).parents[1] / 'migrations/022_partner_request_isolation.sql').read_text()
            conn.exec_driver_sql(isolation_migration)
            conn.exec_driver_sql(isolation_migration)
            for name in ('023_account_emails.sql', '024_application_screening.sql', '025_partner_list_cursor.sql', '026_hiring_access.sql', '028_workspace_invitation_mail.sql', '029_hiring_pricing.sql', '030_billing_delivery.sql', '031_customer_mail.sql'):
                sql = (Path(__file__).parents[1] / 'migrations' / name).read_text()
                conn.exec_driver_sql(sql)
                conn.exec_driver_sql(sql)
        monkeypatch.setattr(database, 'engine', engine)
        monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
        ids = SimpleNamespace(org=uuid.uuid4(), other_org=uuid.uuid4(), role=uuid.uuid4(),
                              other_role=uuid.uuid4(), attempt=uuid.uuid4())
        with database.db_session() as session:
            for uid in ('cook', 'employer', 'other', 'viewer'):
                session.add(User(id=uid, email=f'{uid}@example.test', name=uid,
                                 roles=['cook'] if uid == 'cook' else ['business']))
            session.flush()
            session.add_all([Org(id=ids.org, name='Kitchen'), Org(id=ids.other_org, name='Other kitchen')])
            session.flush()
            session.add_all([OrgMembership(org_id=ids.org, user_id='employer', seat_role='admin'),
                             OrgMembership(org_id=ids.org, user_id='viewer', seat_role='viewer'),
                             OrgMembership(org_id=ids.other_org, user_id='other', seat_role='admin'),
                             RolePosting(id=ids.role, org_id=ids.org, title='Prep cook', status='open'),
                             RolePosting(id=ids.other_role, org_id=ids.other_org, title='Other role', status='open')])
            session.add(SkillAttempt(id=ids.attempt, user_id='cook', session_id='test-session',
                                    verification_state='VERIFIED', metadata_={'recording_generation': '123'},
                                    video_url='https://example.test/locator', authoritative_score=82))
        yield ids
    finally:
        engine.dispose()
        # schema is generated above, never taken from user input or an app database setting.
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setenv('WEBHOOK_SECRET_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('PARTNER_API_KEY_PEPPER', 'test-only-pepper')
    monkeypatch.setattr(auth, '_verify_token', lambda token: {
        'uid': token, 'email': token+'@example.test', 'email_verified': True,
    })
    monkeypatch.setattr(assessment_sharing, 'inspect_recording', lambda *a: ('skill_videos/cook/clip.webm', '123', 'video/webm'))
    monkeypatch.setattr(business, 'playback_url', lambda path, generation, uid: f'https://storage.example.test/{uid}/{generation}')
    monkeypatch.setattr(hiring, '_ensure_cook_profile', lambda *a: None)
    monkeypatch.setattr(hiring.hiring_cv, 'cleanup_on_rollback', lambda *a: None)
    monkeypatch.setattr(hiring.hiring_cv, 'store_cv', lambda aid, data: {'path': f'hiring_cv/{aid}/test.pdf', 'sha256': 'a' * 64, 'generation': '1', 'bytes': len(data)})
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    app.register_blueprint(business.business_bp, url_prefix='/business')
    app.register_blueprint(assessment_sharing.sharing_bp, url_prefix='/sharing')
    app.register_blueprint(skills.skills_bp, url_prefix='/skills')
    app.register_blueprint(hiring.hiring_bp, url_prefix='/hiring')
    app.register_blueprint(stripe_routes.stripe_bp, url_prefix='/stripe')
    app.register_blueprint(embed.embed_bp, url_prefix='/embed')
    app.register_blueprint(partner.partner_bp, url_prefix='/partner')
    app.register_blueprint(cooks.cooks_bp, url_prefix='/cooks')
    return app.test_client()


def headers(uid):
    return {'Authorization': 'Bearer '+uid}


def test_new_employers_activate_separate_workspaces_and_cannot_read_each_others_roles(client, db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from services import hiring_access
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setattr(hiring_access, 'access_allowed', lambda email, **kw: email in ('new-a@example.test', 'new-b@example.test'))
    with database.db_session() as session:
        session.add_all([User(id=uid, email=uid+'@example.test', name=uid, roles=['eater'], active_role='business') for uid in ('new-a', 'new-b', 'unapproved')])
    assert client.post('/business/activate', headers=headers('unapproved'), json={'name':'No access'}).status_code == 403
    def activate(uid):
        with client.application.test_client() as separate:
            response = separate.post('/business/activate', headers=headers(uid), json={'name':uid+' kitchen','city':'Atlanta'})
            assert response.status_code == 200
            return response.json['org']['id']
    with ThreadPoolExecutor(max_workers=4) as pool:
        repeated = list(pool.map(activate, ['new-a'] * 4))
    assert len(set(repeated)) == 1
    other = activate('new-b')
    assert other != repeated[0] and other not in (str(db.org), str(db.other_org))
    assert client.get('/business/org', headers=headers('new-a')).json['org']['id'] == repeated[0]
    assert client.get('/business/org', headers=headers('new-b')).json['org']['id'] == other
    with database.db_session() as session:
        role = RolePosting(org_id=uuid.UUID(repeated[0]), title='Private company role', status='open')
        session.add(role); session.flush(); rid = str(role.id)
        assert session.query(OrgMembership).filter_by(user_id='new-a').count() == 1
    assert client.get('/business/role/'+rid, headers=headers('new-b')).status_code == 404


def test_free_early_integration_preserves_admin_scope_and_enforces_quota(client, db, monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '1')
    monkeypatch.setenv('EARLY_ACCESS_MONTHLY_ASSESSMENT_LIMIT', '1')
    monkeypatch.setattr(partner_integrations, 'enforce_partner_limit', lambda *a: None)
    body = {'name': 'Early-access test key', 'scopes': ['assessments:read', 'assessments:write'], 'environment': 'test'}
    assert client.post('/partner/manage/api-keys', json=body, headers=headers('viewer')).status_code == 403
    issued = client.post('/partner/manage/api-keys', json=body, headers=headers('employer'))
    assert issued.status_code == 201
    key_headers = {'Authorization': 'Bearer '+issued.json['key']['secret']}
    assessment = {'externalJobId': 'early-job', 'jobTitle': 'Prep cook', 'externalCandidateId': 'first',
                  'candidateEmail': 'first@example.test', 'environment': 'test', 'attemptLimit': 3,
                  'assessmentProfileVersion': 'knife-motion-v1',
                  'assessmentCriteria': {'profileVersion': 'knife-motion-v1', 'minimumRhythm': 70}}
    first = client.post('/partner/v1/assessment-requests', json=assessment,
                        headers={**key_headers, 'Idempotency-Key': 'early-first'})
    assert first.status_code == 201
    retry = client.post('/partner/v1/assessment-requests', json=assessment,
                        headers={**key_headers, 'Idempotency-Key': 'early-first'})
    assert retry.status_code == 200
    second = client.post('/partner/v1/assessment-requests', json={**assessment, 'externalCandidateId': 'second'},
                         headers={**key_headers, 'Idempotency-Key': 'early-second'})
    assert second.status_code == 429 and second.json['code'] == 'monthly_limit_reached'
    with database.db_session() as session:
        assert session.get(Org, db.org).plan == 'trial'
        assert session.query(OrgAssessmentUsage).filter_by(org_id=db.org, environment='test').one().request_count == 1
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '0')
    assert client.get('/partner/v1/assessment-requests', headers=key_headers).status_code == 402


def test_bootstrap_email_conflict_never_merges_another_identity(db, client, monkeypatch):
    from routes.auth import auth_bp
    monkeypatch.setenv('AUTH_APP_CHECK_REQUIRED', '0')
    client.application.register_blueprint(auth_bp, url_prefix='/auth')
    with database.db_session() as session:
        session.add(User(id='original-identity', email='new-identity@example.test',
                         name='Original', roles=['eater']))
    response = client.post('/auth/sync', headers=headers('new-identity'),
                           json={'name': 'Replacement', 'createOnly': True})
    assert response.status_code == 409
    assert response.json['code'] == 'account_conflict'
    with database.db_session() as session:
        assert session.get(User, 'new-identity') is None
        assert session.get(User, 'original-identity').name == 'Original'
        assert session.query(EaterProfile).filter_by(user_id='new-identity').count() == 0


def test_simultaneous_account_bootstrap_creates_one_profile_without_losing_signup(db, client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from routes.auth import auth_bp

    monkeypatch.setenv('AUTH_APP_CHECK_REQUIRED', '0')
    client.application.register_blueprint(auth_bp, url_prefix='/auth')
    uid = 'concurrent-new-account'
    barrier = Barrier(4)
    original_get = Session.get

    def synchronized_get(self, entity, ident, **kwargs):
        value = original_get(self, entity, ident, **kwargs)
        if entity is User and ident == uid and value is None and not kwargs.get('populate_existing'):
            barrier.wait(timeout=15)  # Every request sees absence before any inserts.
        return value

    monkeypatch.setattr(Session, 'get', synchronized_get)

    def bootstrap(_):
        with client.application.test_client() as browser:
            return browser.post('/auth/sync', headers=headers(uid), json={
                'name': 'Account recovery', 'activeRole': 'eater', 'createOnly': True,
                'roles': ['business', 'cook'],
            }).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(bootstrap, range(4)))
    assert sorted(statuses) == [200, 200, 200, 201]
    with database.db_session() as session:
        assert session.query(User).filter_by(id=uid).count() == 1
        assert session.query(EaterProfile).filter_by(user_id=uid).count() == 1
        assert session.get(User, uid).roles == ['eater']

    # An explicit signup/profile update can finish after recovery; later recovery
    # calls cannot reset the actual name or employer onboarding choice.
    assert client.post('/auth/sync', headers=headers(uid), json={
        'name': 'Kitchen manager', 'activeRole': 'business', 'phone': '+1 212 555 0100',
    }).status_code == 200
    replay = client.post('/auth/sync', headers=headers(uid), json={
        'name': 'Fallback email name', 'activeRole': 'eater', 'createOnly': True,
    })
    assert replay.status_code == 200
    assert replay.json['name'] == 'Kitchen manager'
    assert replay.json['activeRole'] == 'business'
    assert replay.json['phone'] == '+1 212 555 0100'
    assert replay.json['roles'] == ['eater']


def test_nearby_cooks_use_real_distance_visibility_and_minimal_payload(db, client, monkeypatch):
    from services.location import search_token
    monkeypatch.setenv('LOCATION_TOKEN_SECRET', 'nearby-isolated-secret-' * 3)
    with database.db_session() as session:
        for uid, lng, lat, approved, verified in [
            ('near', -84.39, 33.75, True, True),
            ('far', -74.00, 40.71, True, True),
            ('pending', -84.39, 33.75, False, True),
            ('unverified', -84.39, 33.75, True, False),
        ]:
            session.add(User(id=uid, email=uid+'@example.test', name=uid, roles=['cook']))
            session.flush()
            session.add(CookProfile(user_id=uid, approved=approved, skill_verified=verified,
                skill_score=85, base_location=f'SRID=4326;POINT({lng} {lat})',
                skill_test_result={'private': 'assessment-detail'}, review_note='private-review'))
    body = {'locationToken': search_token(user_id='employer', lat=33.75, lng=-84.39), 'radiusMiles': 5}
    response = client.post('/cooks/nearby', json=body, headers=headers('employer'))
    assert response.status_code == 200
    assert [cook['id'] for cook in response.json['cooks']] == ['near']
    assert response.json['cooks'][0]['distanceIsApproximate'] is True
    assert response.json['cooks'][0]['distanceMiles'] == 0
    assert response.headers['Cache-Control'] == 'no-store'
    assert not {'email', 'baseLocation', 'lat', 'lng', 'skillTestResult', 'reviewNote', 'videoUrl'} & response.json['cooks'][0].keys()
    assert 'private-' not in response.text
    assert client.post('/cooks/nearby', json=body, headers=headers('other')).status_code == 400
    for invalid in ({'radiusMiles': 100000}, {'page': -1}, {'page': True}, {'locationToken': 'forged'}):
        assert client.post('/cooks/nearby', json={**body, **invalid}, headers=headers('employer')).status_code == 400
    assert client.post('/cooks/nearby', json={**body, 'page': 2}, headers=headers('employer')).json['cooks'] == []


def test_service_area_requires_owner_consent_rounds_and_can_be_removed(db, client):
    with database.db_session() as session:
        session.add(CookProfile(user_id='cook', approved=False, skill_verified=False))
    body = {'lat': 33.751234, 'lng': -84.392345}
    assert client.put('/cooks/me/service-area', json=body, headers=headers('cook')).status_code == 400
    body['accepted'] = True
    assert client.put('/cooks/me/service-area', json=body, headers=headers('employer')).status_code == 404
    assert client.put('/cooks/me/service-area', json=body, headers=headers('cook')).status_code == 200
    with database.db_session() as session:
        row = session.execute(text('SELECT ST_X(base_location::geometry), ST_Y(base_location::geometry), approved, skill_verified FROM cook_profiles WHERE user_id=:uid'), {'uid': 'cook'}).one()
        assert tuple(row) == (-84.39, 33.75, False, False)
    assert client.delete('/cooks/me/service-area', headers=headers('cook')).status_code == 200
    with database.db_session() as session:
        assert session.get(CookProfile, 'cook').base_location is None


def grant(client, db, uid='cook', **overrides):
    body = dict(accepted=True, consentVersion=assessment_sharing.CONSENT_VERSION)
    body.update(overrides)
    return client.post(f'/sharing/{db.role}/{db.attempt}', json=body, headers=headers(uid))


def test_share_ownership_revocation_and_tenant_isolation(db, client):
    assert client.get('/business/candidate/cook/video', headers=headers('employer')).status_code == 403
    assert grant(client, db, uid='employer').status_code == 404
    assert grant(client, db, accepted=False).status_code == 400
    response = grant(client, db)
    assert response.status_code == 200
    share_id = response.json['shareId']
    assert grant(client, db).json['shareId'] == share_id
    response = client.get('/business/candidate/cook/video', headers=headers('employer'))
    assert response.status_code == 200
    assert response.json['attemptId'] == str(db.attempt)
    assert response.json['expiresInSeconds'] == 300
    assert response.headers['Cache-Control'] == 'no-store'
    for uid in ('viewer', 'other'):
        assert client.get('/business/candidate/cook/video', headers=headers(uid)).status_code == 403
    assert client.get(f'/business/candidate/cook/video?roleId={db.other_role}', headers=headers('employer')).status_code == 403
    with database.db_session() as session:
        assert session.query(AssessmentShare).count() == 1
        assert session.query(AssessmentAccessLog).count() == 1
    assert client.post(f'/sharing/{share_id}/revoke', headers=headers('employer')).status_code == 404
    assert client.post(f'/sharing/{share_id}/revoke', headers=headers('cook')).status_code == 200
    assert client.post(f'/sharing/{share_id}/revoke', headers=headers('cook')).status_code == 200
    assert client.get('/business/candidate/cook/video', headers=headers('employer')).status_code == 403
    assert grant(client, db).status_code == 409  # delayed consent POST cannot undo revocation


def test_replaced_recording_cannot_inherit_verified_result(db, client, monkeypatch):
    monkeypatch.setattr(assessment_sharing, 'inspect_recording', lambda *a: ('skill_videos/cook/clip.webm', '999', 'video/webm'))
    assert grant(client, db).status_code == 409
    with database.db_session() as session:
        assert session.query(AssessmentShare).count() == 0


def test_viewer_cannot_review_candidates_or_role_pipeline(db, client):
    assert client.get('/business/candidates', headers=headers('viewer')).status_code == 403
    assert client.get(f'/business/role/{db.role}', headers=headers('viewer')).status_code == 403
    assert client.get('/business/shortlist', headers=headers('viewer')).status_code == 403


def test_pipeline_mutation_cannot_create_a_candidate_from_global_cook_id(db, client):
    response = client.post(f'/business/role/{db.role}/stage', json={'cookId': 'cook', 'stage': 'hired'},
                           headers=headers('employer'))
    assert response.status_code == 404
    assert response.json['error'] == 'Candidate has not applied to this role'


def test_browser_cannot_self_grant_paid_plan(db, client):
    response = client.post('/business/plan', json={'plan': 'team'}, headers=headers('employer'))
    assert response.status_code == 409
    with database.db_session() as session:
        assert session.get(Org, db.org).plan in (None, 'trial')


def test_business_checkout_is_admin_only_and_never_grants_plan(db, client, monkeypatch):
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    monkeypatch.setattr(stripe_routes, 'create_billing_customer',
                        lambda **kwargs: 'cus_workspace')
    monkeypatch.setattr(stripe_routes, 'create_subscription_checkout',
                        lambda **kwargs: {'id': 'cs_team', 'url': 'https://checkout.stripe.test/team'})
    from models.billing_catalog import HiringPrice
    with database.db_session() as session:
        row = HiringPrice(plan='team', interval='month', currency='usd', amount=9900, limits={'seats': 5, 'openRoles': 5, 'monthlyRequests': 100}, state='published', active=True, stripe_price_id='price_team', created_by='owner')
        session.add(row); session.flush(); price_id = str(row.id)
    request_id = str(uuid.uuid4())
    assert client.post('/stripe/business/checkout', headers=headers('viewer'),
                       json={'requestId': request_id, 'priceId': price_id}).status_code == 403
    assert client.post('/stripe/business/checkout', headers=headers('employer'),
                       json={'requestId': request_id, 'priceId': str(uuid.uuid4())}).status_code == 409
    response = client.post('/stripe/business/checkout', headers=headers('employer'),
                           json={'requestId': request_id, 'priceId': price_id})
    assert response.status_code == 201
    assert response.json['checkoutUrl'] == 'https://checkout.stripe.test/team'
    with database.db_session() as session:
        org = session.get(Org, db.org)
        assert org.stripe_customer_id == 'cus_workspace'
        assert org.plan in (None, 'trial')


def test_signed_subscription_webhooks_are_idempotent_plan_authority(db, client, monkeypatch):
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    events = [
        {'id': 'evt_active', 'type': 'customer.subscription.updated', 'livemode': False,
         'data': {'object': {
             'id': 'sub_team', 'customer': 'cus_workspace', 'status': 'active',
             'metadata': {'cookcredit_org_id': str(db.org)},
             'items': {'data': [{'price': {'id': 'price_team'}}]},
             'current_period_end': 1893456000, 'cancel_at_period_end': False,
         }}},
        {'id': 'evt_deleted', 'type': 'customer.subscription.deleted', 'livemode': False,
         'data': {'object': {
             'id': 'sub_team', 'customer': 'cus_workspace', 'status': 'canceled',
             'metadata': {'cookcredit_org_id': str(db.org)}, 'items': {'data': []},
         }}},
    ]
    monkeypatch.setattr(stripe_routes, 'construct_webhook_event', lambda *args: events[0])
    monkeypatch.setattr(stripe_routes, 'retrieve_billing_subscription', lambda _: events[0]['data']['object'])
    first = client.post('/stripe/webhook', data=b'signed')
    duplicate = client.post('/stripe/webhook', data=b'signed')
    assert first.status_code == 200
    assert duplicate.json['duplicate'] is True
    with database.db_session() as session:
        org = session.get(Org, db.org)
        assert org.plan == 'team'
        assert org.subscription_status == 'active'
        assert session.query(StripeEvent).count() == 1
    monkeypatch.setattr(stripe_routes, 'construct_webhook_event', lambda *args: events[1])
    monkeypatch.setattr(stripe_routes, 'retrieve_billing_subscription', lambda _: events[1]['data']['object'])
    assert client.post('/stripe/webhook', data=b'signed-deleted').status_code == 200
    with database.db_session() as session:
        org = session.get(Org, db.org)
        assert org.plan == 'trial'
        assert org.subscription_status == 'canceled'
        assert session.query(StripeEvent).count() == 2


def test_delayed_billing_events_use_current_provider_state_and_retry_failures(db, client, monkeypatch):
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    current = {'id': 'sub_current', 'customer': 'cus_workspace', 'status': 'active',
        'metadata': {'cookcredit_org_id': str(db.org)}, 'created': 200,
        'items': {'data': [{'price': {'id': 'price_team'}}]}}
    with database.db_session() as session:
        org = session.get(Org, db.org)
        org.stripe_customer_id = 'cus_workspace'
        org.stripe_subscription_id = 'sub_current'
    monkeypatch.setattr(stripe_routes, 'retrieve_billing_subscription', lambda _: current)
    event = {'id': 'evt_late_checkout', 'type': 'checkout.session.completed', 'livemode': False,
        'data': {'object': {'mode': 'subscription', 'customer': 'cus_workspace', 'subscription': 'sub_current'}}}
    monkeypatch.setattr(stripe_routes, 'construct_webhook_event', lambda *args: event)
    assert client.post('/stripe/webhook', data=b'signed').status_code == 200
    with database.db_session() as session:
        assert session.get(Org, db.org).subscription_status == 'active'
    # An old paid invoice and an old subscription snapshot cannot restore access.
    current['status'] = 'canceled'
    event.update(id='evt_late_invoice', type='invoice.paid')
    event['data']['object'] = {'customer': 'cus_workspace', 'subscription': 'sub_current'}
    assert client.post('/stripe/webhook', data=b'signed').status_code == 200
    event.update(id='evt_stale_active', type='customer.subscription.updated')
    event['data']['object'] = {**current, 'status': 'active'}
    assert client.post('/stripe/webhook', data=b'signed').status_code == 200
    with database.db_session() as session:
        assert session.get(Org, db.org).subscription_status == 'canceled'
        assert session.get(Org, db.org).plan == 'trial'
    def failed(_): raise RuntimeError('provider timeout containing sensitive data')
    monkeypatch.setattr(stripe_routes, 'retrieve_billing_subscription', failed)
    event['id'] = 'evt_retry'
    response = client.post('/stripe/webhook', data=b'signed')
    assert response.status_code == 503 and 'sensitive data' not in response.text
    with database.db_session() as session:
        assert session.get(StripeEvent, 'evt_retry') is None
    monkeypatch.setattr(stripe_routes, 'retrieve_billing_subscription', lambda _: current)
    assert client.post('/stripe/webhook', data=b'signed').status_code == 200
    assert client.post('/stripe/webhook', data=b'signed').json['duplicate'] is True


def test_team_invitation_is_persisted_email_bound_and_accepts_once(db, client, monkeypatch):
    monkeypatch.delenv('SENDGRID_API_KEY', raising=False)
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'team'
        session.add(User(id='invitee', email='invitee@example.test', name='Invitee', roles=['eater']))
    created = client.post('/business/team/invitations', headers=headers('employer'), json={
        'email': 'invitee@example.test', 'seatRole': 'recruiter',
    })
    assert created.status_code == 201
    assert created.json['invitation']['emailDelivered'] is False
    token = created.json['invitation']['inviteUrl'].rsplit('/', 1)[-1]
    assert client.post('/business/team/invitations/accept', headers=headers('other'),
                       json={'token': token}).status_code == 403
    accepted = client.post('/business/team/invitations/accept', headers=headers('invitee'),
                           json={'token': token})
    assert accepted.status_code == 200
    assert accepted.json['seatRole'] == 'recruiter'
    assert client.post('/business/team/invitations/accept', headers=headers('invitee'),
                       json={'token': token}).status_code == 200
    with database.db_session() as session:
        assert session.query(OrgMembership).filter_by(org_id=db.org, user_id='invitee').count() == 1
        assert 'business' in session.get(User, 'invitee').roles
        assert session.query(OrgInvitation).filter_by(status='accepted').count() == 1


def test_application_cursor_pagination_and_city_filter_are_stable(db, client):
    from datetime import timedelta
    now = hiring._utcnow()
    with database.db_session() as session:
        for index, city in enumerate(('Atlanta', 'Brooklyn', 'Atlanta')):
            uid = f'applicant-{index}'
            session.add(User(id=uid, email=f'{uid}@example.test', name=uid, roles=['eater']))
            session.flush()
            session.add(HiringApplication(
                role_posting_id=db.role, applicant_id=uid, status='assessment_required',
                question_schema=[], answers={}, location={'city': city}, attempt_limit=3,
                consent_version=hiring.APPLICATION_CONSENT_VERSION,
                submitted_at=now + timedelta(seconds=index),
            ))
    first = client.get(f'/hiring/roles/{db.role}/applications?limit=2', headers=headers('employer'))
    assert first.status_code == 200
    assert len(first.json['applications']) == 2
    assert first.json['page']['nextCursor']
    second = client.get(
        f"/hiring/roles/{db.role}/applications?limit=2&cursor={first.json['page']['nextCursor']}",
        headers=headers('employer'))
    ids = [item['id'] for item in first.json['applications'] + second.json['applications']]
    assert len(ids) == len(set(ids)) == 3
    atlanta = client.get(f'/hiring/roles/{db.role}/applications?city=atlanta', headers=headers('employer'))
    assert len(atlanta.json['applications']) == 2


def test_origin_bound_widget_uses_org_brand_and_paid_entitlement(db, client):
    settings = {
        'logoUrl': 'https://assets.example.test/kitchen.svg',
        'color': '#245A47',
        'allowedOrigins': ['https://careers.example.test'],
    }
    assert client.patch('/business/integrations', headers=headers('viewer'), json=settings).status_code == 403
    saved = client.patch('/business/integrations', headers=headers('employer'), json=settings)
    assert saved.status_code == 200
    key = saved.json['org']['embed']['key']
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'team'
    allowed = client.get(f'/embed/v1/{key}/roles/{db.role}',
                         headers={'Origin': 'https://careers.example.test'})
    assert allowed.status_code == 200
    assert allowed.headers['Access-Control-Allow-Origin'] == 'https://careers.example.test'
    assert allowed.json['role']['company']['brandColor'] == '#245A47'
    assert allowed.json['role']['company']['logoUrl'].endswith('/kitchen.svg')
    assert client.get(f'/embed/v1/{key}/roles/{db.role}',
                      headers={'Origin': 'https://evil.example'}).status_code == 403
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'trial'
    assert client.get(f'/embed/v1/{key}/roles/{db.role}',
                      headers={'Origin': 'https://careers.example.test'}).status_code == 404


def test_enterprise_api_invitation_and_durable_signed_webhook(db, client, monkeypatch):
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'enterprise'
    hook_response = client.post('/partner/manage/webhooks', headers=headers('employer'), json={
        'url': 'https://hooks.example.test/cookcredit',
        'eventTypes': ['application.submitted'],
    })
    assert hook_response.status_code == 201
    signing_secret = hook_response.json['webhook']['secret']
    assert signing_secret.startswith('whsec_')

    key_response = client.post('/partner/manage/api-keys', headers=headers('employer'), json={
        'name': 'ATS production',
        'scopes': ['roles:read', 'invitations:write', 'applications:read'],
    })
    assert key_response.status_code == 201
    api_key = key_response.json['key']['secret']
    partner_headers = {'Authorization': f'Bearer {api_key}', 'Idempotency-Key': 'candidate-cook-001'}
    roles = client.get('/partner/v1/roles', headers={'Authorization': f'Bearer {api_key}'})
    assert roles.status_code == 200
    assert any(row['id'] == str(db.role) for row in roles.json['data'])

    invite_body = {'roleId': str(db.role), 'candidateEmail': 'cook@example.test',
                   'externalCandidateId': 'ats-candidate-9'}
    invitation = client.post('/partner/v1/assessment-invitations', headers=partner_headers, json=invite_body)
    repeated = client.post('/partner/v1/assessment-invitations', headers=partner_headers, json=invite_body)
    assert invitation.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json['data']['invitationUrl'] == invitation.json['data']['invitationUrl']
    invitation_token = invitation.json['data']['invitationUrl'].split('invite=', 1)[1]

    applied = apply_with_cv(client, f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
        'answers': {}, 'invitationToken': invitation_token,
    })
    assert applied.status_code == 201
    application_id = applied.json['application']['id']
    partner_view = client.get(f'/partner/v1/applications/{application_id}',
                              headers={'Authorization': f'Bearer {api_key}'})
    assert partner_view.status_code == 200
    assert partner_view.json['data']['status'] == 'assessment_required'
    with database.db_session() as session:
        stored_key = session.query(PartnerApiKey).one()
        stored_invite = session.query(PartnerInvitation).one()
        delivery = session.query(PartnerWebhookDelivery).one()
        assert stored_key.secret_hash != api_key
        assert stored_invite.status == 'accepted'
        assert delivery.payload['data']['externalCandidateId'] == 'ats-candidate-9'

    monkeypatch.setattr(partner_integrations, '_assert_public_destination', lambda url: None)
    sent = {}
    def send(url, **kwargs):
        sent.update(url=url, **kwargs)
        return SimpleNamespace(status_code=204)
    stats = partner_integrations.dispatch_partner_webhooks(send=send)
    assert stats == {'claimed': 1, 'delivered': 1, 'failed': 0, 'retrying': 0}
    assert sent['headers']['CookCredit-Signature'].startswith('t=')
    assert ',v1=' in sent['headers']['CookCredit-Signature']
    assert sent['headers']['CookCredit-Event-Id']
    assert signing_secret not in sent['data'].decode()

    key_id = key_response.json['key']['id']
    assert client.post(f'/partner/manage/api-keys/{key_id}/revoke',
                       headers=headers('employer')).status_code == 200
    assert client.get('/partner/v1/roles', headers={'Authorization': f'Bearer {api_key}'}).status_code == 401


def test_universal_assessment_request_reuses_hidden_role_and_external_ids(db, client):
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'integration'
    key_response = client.post('/partner/manage/api-keys', headers=headers('employer'), json={
        'name': 'Universal ATS', 'scopes': ['assessments:read', 'assessments:write'],
    })
    assert key_response.status_code == 201
    api_key = key_response.json['key']['secret']
    auth = {'Authorization': f'Bearer {api_key}', 'Idempotency-Key': 'job-42-candidate-9'}
    body = {
        'externalJobId': 'job-42', 'jobTitle': 'Prep Cook',
        'candidateEmail': 'cook@example.test', 'externalCandidateId': 'candidate-9',
        'attemptLimit': 2, 'returnUrl': 'https://ats.example.test/candidates/9',
        'applicationQuestions': [{'id': 'shift_ok', 'label': 'Can you work evenings?',
                                  'type': 'yes_no', 'required': True}],
    }
    created = client.post('/partner/v1/assessment-requests', headers=auth, json=body)
    repeated = client.post('/partner/v1/assessment-requests', headers=auth, json=body)
    assert created.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json['data']['id'] == created.json['data']['id']
    assert created.json['data']['status'] == 'invited'
    assert created.json['data']['assessmentUrl'].startswith('http')
    assert created.json['data']['externalJobId'] == 'job-42'
    assert created.json['data']['attemptLimit'] == 2

    with database.db_session() as session:
        managed = session.query(RolePosting).filter_by(
            org_id=db.org, external_job_id='job-42', integration_managed=True).all()
        assert len(managed) == 1
        assert managed[0].requirements['applicationQuestions'][0]['id'] == 'shift_ok'
        assert session.query(OrgAssessmentUsage).filter_by(org_id=db.org, environment='live').one().request_count == 1

    request_id = created.json['data']['id']
    fetched = client.get(f'/partner/v1/assessment-requests/{request_id}',
                         headers={'Authorization': f'Bearer {api_key}'})
    assert fetched.status_code == 200
    assert fetched.json['data']['result'] is None
    listed = client.get('/partner/v1/assessment-requests?externalJobId=job-42',
                        headers={'Authorization': f'Bearer {api_key}'})
    assert [row['id'] for row in listed.json['data']] == [request_id]


def test_universal_request_cancel_is_idempotent_and_blocks_accepted_request(db, client):
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'enterprise'
    key_response = client.post('/partner/manage/api-keys', headers=headers('employer'), json={
        'name': 'ATS', 'scopes': ['assessments:read', 'assessments:write'],
    })
    api_key = key_response.json['key']['secret']
    request_headers = {'Authorization': f'Bearer {api_key}', 'Idempotency-Key': 'cancel-me-001'}
    body = {'externalJobId': 'job-cancel', 'jobTitle': 'Line Cook',
            'candidateEmail': 'cook@example.test'}
    created = client.post('/partner/v1/assessment-requests', headers=request_headers, json=body)
    request_id = created.json['data']['id']
    first = client.post(f'/partner/v1/assessment-requests/{request_id}/cancel',
                        headers={'Authorization': f'Bearer {api_key}'})
    second = client.post(f'/partner/v1/assessment-requests/{request_id}/cancel',
                         headers={'Authorization': f'Bearer {api_key}'})
    assert first.status_code == second.status_code == 200
    assert second.json['data']['status'] == 'withdrawn'


def integration_auth(db, client, environment='live'):
    with database.db_session() as session:
        session.get(Org, db.org).plan = 'integration'
    response = client.post('/partner/manage/api-keys', headers=headers('employer'), json={
        'name': 'Integration test', 'environment': environment,
        'scopes': ['assessments:read', 'assessments:write', 'roles:read',
                   'invitations:write', 'applications:read'],
    })
    assert response.status_code == 201
    return {'Authorization': 'Bearer ' + response.json['key']['secret']}


def request_assessment(client, auth_headers, key='request-test-001', **changes):
    return client.post('/partner/v1/assessment-requests',
                       headers={**auth_headers, 'Idempotency-Key': key}, json={
        'externalJobId': 'job-test', 'jobTitle': 'Prep Cook',
        'candidateEmail': 'cook@example.test', **changes,
    })


def invitation_application(client, item, uid='cook', **changes):
    return client.post(f"/hiring/roles/{item['roleId']}/apply", headers=headers(uid), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
        'answers': {}, 'invitationToken': item['assessmentUrl'].split('invite=', 1)[1], **changes,
    })


def test_parallel_partner_retries_charge_and_emit_once(db, client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    auth_headers = integration_auth(db, client)
    assert client.post('/partner/manage/webhooks', headers=headers('employer'), json={
        'url': 'https://hooks.example.test/live', 'eventTypes': ['assessment.invited'],
    }).status_code == 201
    barrier = Barrier(8)
    def submit(_):
        with client.application.test_client() as worker:
            barrier.wait(timeout=10)
            return request_assessment(worker, auth_headers)
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, range(8)))
    assert sorted(r.status_code for r in responses) == [200] * 7 + [201]
    assert len({r.json['data']['assessmentUrl'] for r in responses}) == 1
    with database.db_session() as session:
        assert session.query(PartnerInvitation).count() == 1
        assert session.query(PartnerWebhookDelivery).count() == 1
        assert session.query(OrgAssessmentUsage).one().request_count == 1
    conflict = request_assessment(client, auth_headers, candidateEmail='another@example.test')
    assert conflict.status_code == 409
    assert conflict.json['code'] == 'idempotency_conflict'


def test_partner_cursor_covers_tied_timestamps_and_rejects_scope_changes(db, client):
    from datetime import datetime, timedelta, timezone
    auth_headers = integration_auth(db, client)
    expected = set()
    for index in range(5):
        created = request_assessment(client, auth_headers, key=f'cursor-test-{index}', externalCandidateId=f'candidate-{index}')
        assert created.status_code == 201
        expected.add(created.json['data']['id'])
    with database.db_session() as session:
        session.query(PartnerInvitation).update({'created_at': datetime.now(timezone.utc)-timedelta(days=1)})
    url = '/partner/v1/assessment-requests'
    first = client.get(url, query_string={'limit': 2}, headers=auth_headers)
    assert first.status_code == 200 and len(first.json['data']) == 2
    cursor = first.json['nextCursor']
    for params in ({'limit': 0}, {'limit': 101}, {'cursor': cursor+'bad'},
                   {'cursor': cursor, 'externalJobId': 'changed-filter'}):
        assert client.get(url, query_string=params, headers=auth_headers).status_code == 400
    test_headers = integration_auth(db, client, environment='test')
    assert client.get(url, query_string={'cursor': cursor}, headers=test_headers).status_code == 400
    # Inserts after page one do not duplicate or skip rows already in that scan.
    inserted = request_assessment(client, auth_headers, key='cursor-new-insert', externalCandidateId='new-candidate')
    assert inserted.status_code == 201
    seen = [row['id'] for row in first.json['data']]
    while cursor:
        page = client.get(url, query_string={'limit': 2, 'cursor': cursor}, headers=auth_headers)
        assert page.status_code == 200
        seen.extend(row['id'] for row in page.json['data'])
        cursor = page.json['nextCursor']
    assert set(seen) == expected and len(seen) == 5
    filtered = client.get(url, query_string={'limit': 2, 'status': 'evidence_ready'}, headers=auth_headers)
    assert filtered.json['data'] == [] and filtered.json['hasMore'] is True
    assert filtered.json['nextCursor']


def test_parallel_monthly_limit_and_legacy_endpoint_share_one_allowance(db, client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    monkeypatch.setenv('INTEGRATION_MONTHLY_ASSESSMENT_LIMIT', '3')
    auth_headers = integration_auth(db, client)
    barrier = Barrier(8)
    def submit(index):
        with client.application.test_client() as worker:
            barrier.wait(timeout=10)
            return index, request_assessment(worker, auth_headers, key=f'quota-test-{index}')
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(submit, range(8)))
    assert sorted(r.status_code for _, r in responses) == [201] * 3 + [429] * 5
    winner = next(index for index, r in responses if r.status_code == 201)
    assert request_assessment(client, auth_headers, key=f'quota-test-{winner}').status_code == 200
    legacy = client.post('/partner/v1/assessment-invitations',
                         headers={**auth_headers, 'Idempotency-Key': 'legacy-quota-001'}, json={
        'roleId': str(db.role), 'candidateEmail': 'cook@example.test',
    })
    assert legacy.status_code == 429
    with database.db_session() as session:
        assert session.query(OrgAssessmentUsage).one().request_count == 3
        assert session.query(PartnerInvitation).count() == 3


def test_partner_creation_rollback_does_not_consume_quota(db, client, monkeypatch):
    auth_headers = integration_auth(db, client)
    def fail_event(*args, **kwargs):
        raise RuntimeError('simulated failure before commit')
    with monkeypatch.context() as patch:
        patch.setattr(partner, 'emit_partner_event', fail_event)
        with pytest.raises(RuntimeError, match='simulated failure'):
            request_assessment(client, auth_headers)
    with database.db_session() as session:
        assert session.query(PartnerInvitation).count() == 0
        assert session.query(OrgAssessmentUsage).count() == 0
        assert session.query(RolePosting).filter_by(integration_managed=True).count() == 0
    assert request_assessment(client, auth_headers).status_code == 201


def test_test_keys_and_webhooks_cannot_read_or_change_live_requests(db, client):
    credentials = {env: integration_auth(db, client, env) for env in ('test', 'live')}
    items = {}
    for env in ('test', 'live'):
        hook = client.post('/partner/manage/webhooks', headers=headers('employer'), json={
            'url': 'https://hooks.example.test/events', 'environment': env,
            'eventTypes': ['assessment.invited', 'application.submitted', 'assessment.withdrawn'],
        })
        assert hook.status_code == 201  # Same URL is allowed once per environment.
        response = request_assessment(client, credentials[env])  # Same job and idempotency key.
        assert response.status_code == 201
        items[env] = response.json['data']
    assert items['test']['roleId'] != items['live']['roleId']
    assert client.get('/business/role/' + items['test']['roleId'], headers=headers('employer')).status_code == 404
    for env, other in (('test', 'live'), ('live', 'test')):
        auth_headers = credentials[env]
        listed = client.get('/partner/v1/assessment-requests', headers=auth_headers)
        assert [r['id'] for r in listed.json['data']] == [items[env]['id']]
        path = '/partner/v1/assessment-requests/' + items[other]['id']
        assert client.get(path, headers=auth_headers).status_code == 404
        assert client.post(path + '/cancel', headers=auth_headers).status_code == 404
        assert client.post(path + '/review', headers=auth_headers,
                           json={'decision': 'advance'}).status_code == 404
        assert request_assessment(client, auth_headers, environment=other).status_code == 400
        applied = invitation_application(client, items[env])
        assert applied.status_code == 201
        path = '/partner/v1/applications/' + applied.json['application']['id']
        assert client.get(path, headers=auth_headers).status_code == 200
        assert client.get(path, headers=credentials[other]).status_code == 404
    test_roles = client.get('/partner/v1/roles', headers=credentials['test'])
    assert test_roles.json['data'] == []
    legacy = client.post('/partner/v1/assessment-invitations',
                         headers={**credentials['test'], 'Idempotency-Key': 'test-to-live-001'},
                         json={'roleId': str(db.role), 'candidateEmail': 'cook@example.test'})
    assert legacy.status_code == 404
    with database.db_session() as session:
        deliveries = session.query(PartnerWebhookDelivery).all()
        assert len(deliveries) == 4
        for delivery in deliveries:
            hook = session.get(PartnerWebhook, delivery.webhook_id)
            assert delivery.payload['environment'] == hook.environment
            assert delivery.payload['data']['environment'] == hook.environment
            assert delivery.payload['data']['assessmentRequestId'] == items[hook.environment]['id']
        assert sorted(row.request_count for row in session.query(OrgAssessmentUsage)) == [1, 1]


def test_invitation_access_cancellation_expiry_and_accepted_retries(db, client):
    from datetime import timedelta
    auth_headers = integration_auth(db, client)
    item = request_assessment(client, auth_headers).json['data']
    assert client.get('/hiring/roles/' + item['roleId']).status_code == 404
    assert invitation_application(client, item, invitationToken='').status_code == 409
    assert invitation_application(client, item, uid='other').status_code == 403
    path = '/partner/v1/assessment-requests/' + item['id'] + '/cancel'
    assert client.post(path, headers=auth_headers).status_code == 200
    assert invitation_application(client, item).status_code == 409
    token = item['assessmentUrl'].split('invite=', 1)[1]
    assert client.get(f"/hiring/roles/{item['roleId']}?invite={token}").status_code == 409
    item = request_assessment(client, auth_headers, key='expiring-002').json['data']
    with database.db_session() as session:
        session.get(PartnerInvitation, uuid.UUID(item['id'])).expires_at = hiring._utcnow() - timedelta(seconds=1)
    assert invitation_application(client, item).status_code == 409
    item = request_assessment(client, auth_headers, key='accepted-003').json['data']
    assert invitation_application(client, item).status_code == 201
    path = '/partner/v1/assessment-requests/' + item['id'] + '/cancel'
    assert client.post(path, headers=auth_headers).status_code == 409
    assert invitation_application(client, item).status_code in (200, 201)


def test_invitation_questions_and_attempts_are_frozen_before_application(db, client):
    auth_headers = integration_auth(db, client)
    questions = [{'id': 'shift_ok', 'label': 'Available evenings?', 'type': 'yes_no', 'required': True}]
    first = request_assessment(client, auth_headers, attemptLimit=1, jobTitle='First title',
                               applicationQuestions=questions, locationLabel='Brooklyn').json['data']
    changed = request_assessment(client, auth_headers, key='new-candidate-002',
                                 candidateEmail='other@example.test', attemptLimit=3)
    assert changed.status_code == 201
    assert changed.json['data']['roleId'] == first['roleId']
    token = first['assessmentUrl'].split('invite=', 1)[1]
    public = client.get(f"/hiring/roles/{first['roleId']}?invite={token}").json['role']
    assert public['title'] == 'First title'
    assert public['questions'][0]['id'] == 'shift_ok'
    assert public['attemptLimit'] == 1
    assert public['location']['label'] == 'Brooklyn'
    assert invitation_application(client, first).status_code == 400
    submitted = invitation_application(client, first, answers={'shift_ok': True}, location={'city': 'Brooklyn'})
    assert submitted.status_code == 201
    assert submitted.json['application']['attemptLimit'] == 1
    assert submitted.json['application']['questions'][0]['id'] == 'shift_ok'
    assert submitted.json['application']['answers'] == {'shift_ok': True}
    another = request_assessment(client, auth_headers, key='same-candidate-003').json['data']
    assert invitation_application(client, another).status_code == 409


def test_invalid_integration_settings_are_client_errors(db, client):
    auth_headers = integration_auth(db, client)
    for scopes in ([], [{}]):
        assert client.post('/partner/manage/api-keys', headers=headers('employer'), json={
            'name': 'Invalid', 'scopes': scopes,
        }).status_code == 400
    for events in ('assessment.invited', [{}]):
        assert client.post('/partner/manage/webhooks', headers=headers('employer'), json={
            'url': 'https://hooks.example.test/events', 'eventTypes': events,
        }).status_code == 400
    assert request_assessment(client, auth_headers, applicationQuestions=[{
        'id': 'choices', 'label': 'Choice', 'type': 'select', 'options': 'AB',
    }]).status_code == 400


def test_migration_status_does_not_write_schema(db, monkeypatch, capsys):
    from migrations import run_migrations
    monkeypatch.setattr(run_migrations, 'discover', lambda: [('999_status.sql', 'unused')])
    with database.engine.connect() as conn:
        assert run_migrations.run(conn, status_only=True) == 0
        assert conn.exec_driver_sql("SELECT to_regclass(quote_ident(current_schema()) || '.schema_migrations')").scalar() is None
    assert '1 total, 0 applied, 1 pending' in capsys.readouterr().out


def test_account_email_concurrent_enqueue_is_deduplicated(db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    from models.account_email import AccountEmail
    from services import account_email
    monkeypatch.setattr(account_email, 'utcnow', lambda: datetime(2026, 9, 18, tzinfo=timezone.utc))
    def enqueue(_):
        with database.db_session() as session:
            account_email.enqueue_account_email(session, kind='welcome',
                recipient='cook@example.test', user_id='cook')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(enqueue, range(16)))
    with database.db_session() as session:
        assert session.query(AccountEmail).count() == 1
        assert session.query(AccountEmail).one().status == 'pending'


def test_account_email_workers_claim_disjoint_batches(db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from models.account_email import AccountEmail
    from services import account_email
    with database.db_session() as session:
        for index in range(4):
            account_email.enqueue_account_email(session, kind='reset', recipient=f'load-{index}@example.test')
    barrier, lock, recipients = Barrier(4), Lock(), []
    def deliver(item):
        barrier.wait(timeout=10)
        with lock:
            recipients.append(item.recipient)
        return 'sent'
    monkeypatch.setattr(account_email, 'deliver_account_email', deliver)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: account_email.dispatch_account_emails(limit=2), range(2)))
    assert sum(result['sent'] for result in results) == 4
    assert len(set(recipients)) == len(recipients) == 4
    with database.db_session() as session:
        assert {row.status for row in session.query(AccountEmail)} == {'sent'}
        assert {row.attempts for row in session.query(AccountEmail)} == {1}


def test_account_email_failure_backoff_and_crashed_lease_exhaustion(db, monkeypatch):
    from datetime import timedelta
    from models.account_email import AccountEmail
    from services import account_email
    with database.db_session() as session:
        account_email.enqueue_account_email(session, kind='verify', recipient='cook@example.test', user_id='cook')
    def offline(_):
        raise RuntimeError('Provider exception with information that must not be persisted')
    monkeypatch.setattr(account_email, 'deliver_account_email', offline)
    assert account_email.dispatch_account_emails()['failed'] == 1
    assert account_email.dispatch_account_emails()['claimed'] == 0
    with database.db_session() as session:
        row = session.query(AccountEmail).one()
        assert row.status == 'pending'
        assert row.last_error == 'delivery_failed'
        assert row.available_at > account_email.utcnow()
        row.status = 'sending'
        row.attempts = 8
        row.lease_token = uuid.uuid4()
        row.lease_until = account_email.utcnow() - timedelta(seconds=1)
    assert account_email.dispatch_account_emails()['claimed'] == 0
    with database.db_session() as session:
        row = session.query(AccountEmail).one()
        assert row.status == 'failed'
        assert row.lease_token is None
        assert row.last_error == 'delivery_lease_expired'


def test_criteria_are_frozen_and_shared_by_api_filter_and_webhook(db, client, monkeypatch):
    from datetime import timedelta
    from services.hiring_applications import sync_application
    monkeypatch.delenv('ASSESSMENT_EMPLOYMENT_VALIDATED', raising=False)
    partner_headers = integration_auth(db, client)
    assert client.post('/partner/manage/webhooks', headers=headers('employer'), json={
        'url': 'https://hooks.example.test/criteria', 'eventTypes': ['assessment.evidence_ready'],
    }).status_code == 201
    first = request_assessment(client, partner_headers, assessmentCriteria={'profileVersion': 'knife-motion-v1', 'minimumRhythm': 75})
    assert first.status_code == 201
    item = first.json['data']
    assert request_assessment(client, partner_headers,
        assessmentCriteria={'profileVersion': 'knife-motion-v1', 'minimumRhythm': 90}).status_code == 409
    assert request_assessment(client, partner_headers, key='another-applicant-criteria',
        candidateEmail='other@example.test', assessmentCriteria={'profileVersion': 'knife-motion-v1', 'minimumRhythm': 90}).status_code == 201
    applied = invitation_application(client, item)
    assert applied.status_code == 201
    aid = uuid.UUID(applied.json['application']['id'])
    assert applied.json['application']['assessmentCriteria']['minimumRhythm'] == 75
    with database.db_session() as session:
        application = session.get(HiringApplication, aid)
        role = session.get(RolePosting, application.role_posting_id)
        role.requirements = {**role.requirements, 'assessmentCriteria': {'profileVersion': 'knife-motion-v1', 'minimumRhythm': 95}}
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.server_block = {'verdict': {'technique_ok': True}, 'product_half': {'ok': True}}
        attempt.metadata_ = {**attempt.metadata_, 'assessment_criteria': application.assessment_criteria}
        session.add(HiringAssessmentSession(application_id=aid, applicant_id='cook', slot=1,
            status='processing', attempt_id=attempt.id, expires_at=hiring._utcnow() + timedelta(hours=1)))
        session.flush()
        sync_application(session, application)
    result = client.get(f"/partner/v1/assessment-requests/{item['id']}", headers=partner_headers).json['data']['result']
    assert result['outcome'] == 'review_required'
    assert result['profile']['criteria']['minimumRhythm'] == 75
    assert result['attemptsRemaining'] == 2
    assert result['workflowGate']['humanDecisionRequired'] is True
    listed = client.get(f"/hiring/roles/{item['roleId']}/applications?outcome=review_required", headers=headers('employer'))
    assert [row['id'] for row in listed.json['applications']] == [str(aid)]
    assert client.get(f"/hiring/roles/{item['roleId']}/applications?outcome=not_demonstrated",
        headers=headers('employer')).json['applications'] == []
    with database.db_session() as session:
        delivery = session.query(PartnerWebhookDelivery).filter_by(event_type='assessment.evidence_ready').one()
        assert delivery.payload['data']['result'] == result


def test_public_application_requires_verified_email(db, client, monkeypatch):
    monkeypatch.setattr(auth, '_verify_token', lambda token: {
        'uid': 'cook', 'email': 'cook@example.test', 'email_verified': False,
    })
    response = apply_with_cv(client, f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
    })
    assert response.status_code == 403
    with database.db_session() as session:
        assert session.query(HiringApplication).count() == 0


def test_webhook_batch_sends_concurrently_with_a_batch_sized_lease(db, client, monkeypatch):
    from threading import Barrier
    integration_auth(db, client)
    assert client.post('/partner/manage/webhooks', headers=headers('employer'), json={
        'url': 'https://hooks.example.test/batch', 'eventTypes': ['assessment.invited'],
    }).status_code == 201
    with database.db_session() as session:
        for index in range(5):
            partner_integrations.emit_partner_event(session, org_id=db.org,
                event_type='assessment.invited', data={'syntheticIndex': index})
    barrier = Barrier(5)
    monkeypatch.setattr(partner_integrations, '_assert_public_destination', lambda _: None)
    def send(*args, **kwargs):
        barrier.wait(timeout=10)
        with database.db_session() as session:
            import json
            event_id = uuid.UUID(json.loads(kwargs['data'])['id'])
            row = session.query(PartnerWebhookDelivery).filter_by(event_id=event_id).one()
            # Other sends may already have committed independently. This send
            # must retain its own lease until its HTTP request completes.
            assert row.status == 'delivering'
            assert (row.locked_until - partner_integrations._utcnow()).total_seconds() > 120
        assert kwargs['stream'] is True
        return SimpleNamespace(status_code=204)
    assert partner_integrations.dispatch_partner_webhooks(send=send) == {
        'claimed': 5, 'delivered': 5, 'failed': 0, 'retrying': 0,
    }


def test_migration_and_marker_rollback_together(db):
    from migrations import run_migrations
    from sqlalchemy.exc import DBAPIError
    with database.engine.connect() as conn:
        conn.exec_driver_sql('CREATE TABLE schema_migrations(filename TEXT PRIMARY KEY)')
        conn.commit()
        with pytest.raises(DBAPIError):
            run_migrations.apply_migration(conn, '999_failure.sql',
                '-- test outer transaction\nBEGIN;\nCREATE TABLE atomic_migration(id INT);\nSELECT 1/0;\nCOMMIT;\n')
        assert conn.exec_driver_sql("SELECT to_regclass('atomic_migration')").scalar() is None
        assert conn.exec_driver_sql('SELECT count(*) FROM schema_migrations').scalar() == 0
        conn.commit()
        run_migrations.apply_migration(conn, '999_failure.sql', 'CREATE TABLE atomic_migration(id INT);')
        with pytest.raises(DBAPIError):
            run_migrations.apply_migration(conn, '999_failure.sql', 'CREATE TABLE marker_failure(id INT);')
        assert conn.exec_driver_sql("SELECT to_regclass('marker_failure')").scalar() is None
        assert conn.exec_driver_sql('SELECT count(*) FROM schema_migrations').scalar() == 1


def test_concurrent_migration_runners_apply_non_idempotent_sql_once(db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from unittest.mock import mock_open
    from migrations import run_migrations
    monkeypatch.setattr(run_migrations, 'discover', lambda: [('999_once.sql', 'unused')])
    monkeypatch.setattr(run_migrations, 'open', mock_open(read_data=(
        'BEGIN;\nCREATE TABLE migration_once(id INT);\n'
        'INSERT INTO migration_once VALUES (1);\nSELECT pg_sleep(0.1);\nCOMMIT;\n'
    )), raising=False)
    barrier = Barrier(2)
    def migrate(_):
        with database.engine.connect() as conn:
            barrier.wait(timeout=10)
            return run_migrations.run(conn)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(migrate, range(2))) == [0, 0]
    with database.engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT count(*) FROM migration_once').scalar() == 1
        assert conn.exec_driver_sql('SELECT count(*) FROM schema_migrations').scalar() == 1


def test_scoring_outage_remains_retryable(db, client, monkeypatch):
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.verification_state = 'PROVISIONAL'
    def unavailable(*a, **kw):
        raise skill_attempts.ScoringError('storage unavailable')
    result = skill_attempts.run_recompute(str(db.attempt), fetch_video=unavailable)
    assert result is None
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.verification_state == 'VERIFYING'
        assert attempt.recompute_count == 1
        assert session.query(SkillAttemptEvent).count() == 1


def test_concurrent_delivery_does_not_duplicate_processing(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    started, release = Event(), Event()
    with database.db_session() as session:
        session.get(SkillAttempt, db.attempt).verification_state = 'PROVISIONAL'
    def slow_fetch(*a, **kw):
        started.set()
        assert release.wait(10)
        raise skill_attempts.ScoringError('simulated temporary outage')
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(skill_attempts.run_recompute, str(db.attempt), fetch_video=slow_fetch)
        try:
            assert started.wait(10)
            with pytest.raises(skill_attempts.RecomputeBusy):
                skill_attempts.run_recompute(str(db.attempt), fetch_video=slow_fetch)
        finally:
            release.set()
        assert first.result(timeout=10) is None
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.recompute_count == 1
        assert attempt.recompute_lease_id is None


def test_concurrent_submissions_create_one_attempt_and_event(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    def submit():
        barrier.wait(timeout=10)
        with database.db_session() as session:
            attempt, created = skill_attempts.create_or_get_attempt(
                session, user_id='cook', session_id='concurrent-session', profile_id='guillotine_dice',
                on_device_score=None, on_device_block={}, local_result={}, trajectory=[],
                metadata={}, video_url=None)
            return str(attempt.id), created
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: submit(), range(2)))
    assert a[0] == b[0]
    assert sorted([a[1], b[1]]) == [False, True]
    with database.db_session() as session:
        assert session.query(SkillAttemptEvent).filter_by(attempt_id=uuid.UUID(a[0])).count() == 1


def make_due(db):
    from datetime import datetime, timedelta, timezone
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        attempt.verification_state = 'PROVISIONAL'
        attempt.dispatch_due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        attempt.authoritative_score = None


def test_submission_commits_dispatch_intent_without_queue_call(db, client, monkeypatch):
    import json
    monkeypatch.setattr(skills, 'score_trajectory', lambda _: {})
    monkeypatch.setattr(skills, 'owned_recording_path', lambda *a: 'skill_videos/cook/new.webm')
    monkeypatch.setattr(skills, 'inspect_recording', lambda *a: ('skill_videos/cook/new.webm', '456', 'video/webm'))
    monkeypatch.setattr(skill_attempts, 'enqueue_recompute', lambda *a, **kw: pytest.fail('request must not dispatch'))
    body = {'payload': json.dumps(dict(session_id='durable-session', trajectory=[], metadata={},
                                       video_url='https://example.test/recording'))}
    response = client.post('/skills/submit', data=body, headers=headers('cook'))
    assert response.status_code == 201
    retry = client.post('/skills/submit', data=body, headers=headers('cook'))
    assert retry.status_code == 200
    assert response.json['attempt_id'] == retry.json['attempt_id']
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, uuid.UUID(response.json['attempt_id']))
        assert attempt.dispatch_due_at is not None
        assert attempt.metadata_['recording_generation'] == '456'
        assert session.query(SkillAttemptEvent).filter_by(attempt_id=attempt.id).count() == 1


def test_submission_rollback_does_not_leave_dispatch_work(db):
    with pytest.raises(RuntimeError):
        with database.db_session() as session:
            skill_attempts.create_or_get_attempt(session, user_id='cook', session_id='rolled-back',
                profile_id='guillotine_dice', on_device_score=None, on_device_block={},
                local_result={}, trajectory=[], metadata={'recording_generation': '1'}, video_url='locator')
            raise RuntimeError('crash before commit')
    with database.db_session() as session:
        assert session.query(SkillAttempt).filter_by(session_id='rolled-back').count() == 0


def test_queue_outage_is_recovered_without_applicant_retry(db):
    make_due(db)
    def offline(*a, **kw):
        raise RuntimeError('queue unavailable')
    assert scoring_dispatch.drain_scoring_dispatch(send=offline)['failed'] == 1
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.dispatch_failures == 1
        assert attempt.recompute_count == 0  # Infrastructure outage consumes no scoring attempt.
        assert attempt.dispatch_due_at > skill_attempts._utcnow()
    make_due(db)
    delivered = []
    assert scoring_dispatch.drain_scoring_dispatch(send=lambda *a, **kw: delivered.append((a, kw)))['delivered'] == 1
    assert len(delivered) == 1
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.dispatch_failures == 0
        assert attempt.dispatch_due_at is not None  # Still recoverable if queue loses the task.


def test_dispatch_crash_or_lost_task_uses_fresh_recovery_name(db):
    make_due(db)
    names = []
    class ProcessStopped(BaseException):
        pass
    def stop_after_sending(aid, *, dispatch_id):
        names.append(dispatch_id)
        raise ProcessStopped()
    with pytest.raises(ProcessStopped):
        scoring_dispatch.drain_scoring_dispatch(send=stop_after_sending)
    assert scoring_dispatch.drain_scoring_dispatch(send=lambda *a, **kw: pytest.fail('lease active'))['claimed'] == 0
    make_due(db)  # Simulate expiry of dispatch lease.
    assert scoring_dispatch.drain_scoring_dispatch(send=lambda aid, **kw: names.append(kw['dispatch_id']))['delivered'] == 1
    make_due(db)  # Successful enqueue, but no worker ever received it.
    assert scoring_dispatch.drain_scoring_dispatch(send=lambda aid, **kw: names.append(kw['dispatch_id']))['delivered'] == 1
    assert len(set(names)) == 3


def test_concurrent_dispatchers_and_worker_completion(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    make_due(db)
    entered, release = Event(), Event()
    def send(aid, **kw):
        entered.set()
        assert release.wait(10)
        # Worker finishes before the dispatch API returns. Its terminal state wins.
        skill_attempts.run_recompute(aid, fetch_video=lambda *a, **kw: (b'clip', 'video/webm'),
                                     score_video=lambda *a, **kw: {})
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(scoring_dispatch.drain_scoring_dispatch, send=send)
        try:
            assert entered.wait(10)
            assert scoring_dispatch.drain_scoring_dispatch(send=lambda *a, **kw: pytest.fail('duplicate'))['claimed'] == 0
        finally:
            release.set()
        assert future.result(timeout=10)['delivered'] == 1
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.verification_state == 'INSUFFICIENT'
        assert attempt.dispatch_due_at is None
        assert attempt.dispatch_token is None


def test_expired_worker_lease_recovers_and_stale_result_cannot_publish(db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from datetime import timedelta
    make_due(db)
    entered, release = Event(), Event()
    def slow_score(*a, **kw):
        entered.set()
        assert release.wait(10)
        return {'motion_half': {'technique': 'guillotine', 'candidate': 'guillotine'},
                'product_half': {'ok': True}, 'verdict': {'technique_ok': True, 'product_score': .9}}
    fetch = lambda *a, **kw: (b'clip', 'video/webm')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(skill_attempts.run_recompute, str(db.attempt), fetch_video=fetch, score_video=slow_score)
        try:
            assert entered.wait(10)
            assert scoring_dispatch.drain_scoring_dispatch(send=lambda *a, **kw: pytest.fail('worker live'))['claimed'] == 0
            with database.db_session() as session:
                attempt = session.get(SkillAttempt, db.attempt)
                attempt.recompute_lease_until = skill_attempts._utcnow() - timedelta(seconds=1)
                attempt.dispatch_due_at = attempt.recompute_lease_until
            def recover(aid, **kw):
                skill_attempts.run_recompute(aid, fetch_video=fetch, score_video=lambda *a, **kw: {})
            assert scoring_dispatch.drain_scoring_dispatch(send=recover)['delivered'] == 1
        finally:
            release.set()
        future.result(timeout=10)
    with database.db_session() as session:
        attempt = session.get(SkillAttempt, db.attempt)
        assert attempt.verification_state == 'INSUFFICIENT'
        assert attempt.authoritative_score is None
        assert attempt.recompute_count == 2
        assert session.query(SkillAttemptEvent).filter_by(attempt_id=db.attempt, to_state='INSUFFICIENT').count() == 1


def test_repeated_worker_crashes_have_bounded_processing_cost(db):
    make_due(db)
    with database.db_session() as session:
        session.get(SkillAttempt, db.attempt).recompute_count = skill_attempts.MAX_RECOMPUTES
    result = skill_attempts.run_recompute(str(db.attempt), fetch_video=lambda *a, **kw: pytest.fail('budget exhausted'))
    assert result.verification_state == 'INSUFFICIENT'
    assert result.authoritative_score is None
    assert result.dispatch_due_at is None


def test_configurable_application_and_three_attempt_limit(db, client, monkeypatch):
    with database.db_session() as session:
        role = session.get(RolePosting, db.role)
        role.requirements = {
            'attemptLimit': 3,
            'locationLabel': 'Brooklyn, NY',
            'applicationQuestions': [
                {'id': 'availability', 'label': 'Can you work evenings?', 'type': 'yes_no',
                 'required': True, 'options': []},
                {'id': 'station', 'label': 'Preferred station', 'type': 'select',
                 'required': True, 'options': ['Prep', 'Line']},
            ],
        }
    role_response = client.get(f'/hiring/roles/{db.role}')
    assert role_response.status_code == 200
    assert role_response.json['role']['attemptLimit'] == 3
    assert role_response.json['role']['location']['label'] == 'Brooklyn, NY'
    bad = apply_with_cv(client, f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
        'answers': {'availability': True},
    })
    assert bad.status_code == 400
    applied = apply_with_cv(client, f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
        'answers': {'availability': True, 'station': 'Prep'},
        'location': {'city': 'Brooklyn', 'lat': 40.67821, 'lng': -73.94418},
    })
    assert applied.status_code == 201
    application_id = applied.json['application']['id']
    assert applied.json['application']['location'] == {'city': 'Brooklyn', 'lat': 40.678, 'lng': -73.944}
    with database.db_session() as session:
        application = session.get(HiringApplication, uuid.UUID(application_id))
        assert application.question_schema[0]['label'] == 'Can you work evenings?'
        assert session.query(PipelineCard).filter_by(role_posting_id=db.role, cook_id='cook').count() == 1
        assert session.query(HiringApplicationEvent).filter_by(event_type='application_submitted').count() == 1

    evidence_number = 0
    def verified_evidence(uid, assessment_id):
        nonlocal evidence_number
        evidence_number += 1
        return {
            'assessmentId': assessment_id,
            'locator': 'https://example.test/owned',
            'storagePath': f'cookcredit-skill/users/{uid}/assessments/{assessment_id}/recording.webm',
            'generation': str(evidence_number), 'contentType': 'video/webm',
            'onDevice': {'score': 70 + evidence_number, 'metrics': {}},
            'metadata': {'cut': 'dice', 'schema': 'engine-cloud-1'},
        }
    monkeypatch.setattr(hiring, 'verified_engine_assessment', verified_evidence)
    for slot in (1, 2, 3):
        started = client.post(f'/hiring/applications/{application_id}/attempts/start', headers=headers('cook'))
        assert started.status_code == 201
        assert started.json['slot'] == slot
        # Repeated start returns the one active reservation, not another slot.
        repeated = client.post(f'/hiring/applications/{application_id}/attempts/start', headers=headers('cook'))
        assert repeated.status_code == 200
        assert repeated.json['sessionId'] == started.json['sessionId']
        completed = client.post(f"/hiring/assessment-sessions/{started.json['sessionId']}/complete",
                                headers=headers('cook'), json={'assessmentId': f'engine-{slot}'})
        assert completed.status_code == 202
        with database.db_session() as session:
            attempt = session.get(SkillAttempt, uuid.UUID(completed.json['attemptId']))
            assert attempt.dispatch_due_at is not None
            attempt.verification_state = 'INSUFFICIENT'
        status = client.get(f'/hiring/applications/{application_id}', headers=headers('cook'))
        assert status.status_code == 200
        assert status.json['application']['attemptsCompleted'] == slot
    exhausted = client.post(f'/hiring/applications/{application_id}/attempts/start', headers=headers('cook'))
    assert exhausted.status_code == 409
    assert exhausted.json['error'] == 'All assessment attempts have been used'
    employer = client.get(f'/hiring/roles/{db.role}/applications', headers=headers('employer'))
    assert employer.status_code == 200
    assert employer.json['applications'][0]['attemptsRemaining'] == 0
    assert employer.json['applications'][0]['bestAssessment'] is None


@pytest.mark.parametrize('during_import', [False, True])
def test_withdrawn_application_cannot_attach_a_recording(db, client, monkeypatch, during_import):
    applied = apply_with_cv(client, f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
        'answers': {},
    })
    assert applied.status_code == 201
    application_id = applied.json['application']['id']
    started = client.post(f'/hiring/applications/{application_id}/attempts/start', headers=headers('cook'))
    assert started.status_code == 201
    def withdraw():
        with database.db_session() as session:
            session.get(HiringApplication, uuid.UUID(application_id)).status = 'withdrawn'
    def evidence(*args, **kwargs):
        assert during_import, 'A withdrawn application must not read the live recording'
        withdraw()
        return {}
    monkeypatch.setattr(hiring, 'verified_engine_assessment', evidence)
    if not during_import:
        withdraw()
    result = client.post(f'/hiring/assessment-sessions/{started.json["sessionId"]}/complete',
                         headers=headers('cook'), json={'assessmentId': 'owned-record'})
    assert result.status_code == 409
    with database.db_session() as session:
        handoff = session.get(HiringAssessmentSession, uuid.UUID(started.json['sessionId']))
        assert handoff.attempt_id is None and handoff.status == 'started'


def test_application_schema_is_snapshotted(db, client):
    with database.db_session() as session:
        session.get(RolePosting, db.role).requirements = {
            'attemptLimit': 2,
            'applicationQuestions': [{'id': 'first_question', 'label': 'Original question',
                                      'type': 'short_text', 'required': True, 'options': []}],
        }
    response = apply_with_cv(client, f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
        'answers': {'first_question': 'Original answer'},
    })
    assert response.status_code == 201
    aid = uuid.UUID(response.json['application']['id'])
    with database.db_session() as session:
        session.get(RolePosting, db.role).requirements = {'attemptLimit': 1, 'applicationQuestions': []}
        application = session.get(HiringApplication, aid)
        assert application.attempt_limit == 2
        assert application.question_schema[0]['label'] == 'Original question'
        assert application.answers == {'first_question': 'Original answer'}


def test_live_worker_requires_motion_review_and_withdrawal_revokes_access(db, client, monkeypatch):
    monkeypatch.setattr(skill_attempts, '_stamp_credential', lambda *args: None)
    applied = apply_with_cv(client, f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json={
        'acceptedEvidenceShare': True, 'consentVersion': hiring.APPLICATION_CONSENT_VERSION,
        'answers': {},
    })
    assert applied.status_code == 201
    application_id = applied.json['application']['id']
    assert client.get(f'/hiring/roles/{db.role}/my-application', headers=headers('cook')).json['application']['id'] == application_id

    monkeypatch.setenv('FRONTEND_URL', 'https://foodnlit-1123e.web.app')
    monkeypatch.setenv('PUBLIC_API_URL', 'https://cookcredit-api-eqqoi6wp6a-uc.a.run.app')
    started = client.post(f'/hiring/applications/{application_id}/attempts/start', headers=headers('cook'))
    assert started.status_code == 201
    assert f'%2Fapplication-assessment-return%2F{started.json["sessionId"]}' in started.json['launchUrl']
    status = client.get(f'/hiring/assessment-sessions/{started.json["sessionId"]}', headers=headers('cook'))
    assert status.status_code == 200
    assert status.json['session']['applicationId'] == application_id
    assert client.get(f'/hiring/assessment-sessions/{started.json["sessionId"]}', headers=headers('employer')).status_code == 404

    monkeypatch.setattr(hiring, 'verified_engine_assessment', lambda uid, assessment_id: {
        'assessmentId': assessment_id,
        'locator': 'https://storage.example.test/owned',
        'storagePath': f'cookcredit-skill/users/{uid}/assessments/{assessment_id}/recording.webm',
        'generation': '777', 'contentType': 'video/webm',
        'onDevice': {'score': 91, 'metrics': {'rhythm': 90}},
        'metadata': {'cut': 'dice', 'schema': 'engine-cloud-1'},
    })
    completed = client.post(f'/hiring/assessment-sessions/{started.json["sessionId"]}/complete',
                            headers=headers('cook'), json={'assessmentId': 'engine-worker-result'})
    assert completed.status_code == 202
    attempt_id = completed.json['attemptId']
    skill_attempts.run_recompute(
        attempt_id,
        fetch_video=lambda *args, **kwargs: (b'owned-video', 'video/webm'),
        score_video=lambda *args, **kwargs: pytest.fail('The dice scorer must not process a wrist-motion assessment'))
    with database.db_session() as session:
        application = session.get(HiringApplication, uuid.UUID(application_id))
        handoff = session.query(HiringAssessmentSession).filter_by(application_id=application.id).one()
        assert application.status == 'ready'
        assert handoff.status == 'completed'
        assert session.query(AssessmentShare).filter_by(role_posting_id=db.role, applicant_id='cook').count() == 1
        assert session.query(PipelineCard).filter_by(role_posting_id=db.role, cook_id='cook').one().stage == 'assessing'
        assert session.get(SkillAttempt, uuid.UUID(attempt_id)).authoritative_score is None

    withdrawn = client.post(f'/hiring/applications/{application_id}/withdraw', headers=headers('cook'))
    assert withdrawn.status_code == 200
    assert withdrawn.json['application']['status'] == 'withdrawn'
    with database.db_session() as session:
        share = session.query(AssessmentShare).filter_by(role_posting_id=db.role, applicant_id='cook').one()
        assert share.revoked_at is not None
    employer = client.get(f'/hiring/roles/{db.role}/applications', headers=headers('employer'))
    assert employer.json['applications'][0]['status'] == 'withdrawn'
    assert employer.json['applications'][0]['bestAssessment'] is None


def test_applicant_account_list_is_private_and_resumes_closed_roles(db, client):
    with database.db_session() as session:
        for index in range(3):
            role = RolePosting(id=uuid.uuid4(), org_id=db.org, title=f'Cook {index}', status='open')
            session.add(role); session.flush()
            session.add(HiringApplication(role_posting_id=role.id, applicant_id='cook',
                consent_version=hiring.APPLICATION_CONSENT_VERSION, answers={}, question_schema=[],
                status='assessment_required', attempt_limit=3))
        session.flush()
    first = client.get('/hiring/my-applications?limit=2', headers=headers('cook'))
    assert first.status_code == 200 and len(first.json['applications']) == 2
    assert first.headers['Cache-Control'] == 'no-store'
    second = client.get('/hiring/my-applications?limit=2&cursor='+first.json['page']['nextCursor'], headers=headers('cook'))
    assert len(second.json['applications']) == 1
    assert not set(row['id'] for row in first.json['applications']) & set(row['id'] for row in second.json['applications'])
    assert client.get('/hiring/my-applications', headers=headers('other')).json['applications'] == []
    selected = first.json['applications'][0]
    with database.db_session() as session:
        session.get(RolePosting, uuid.UUID(selected['role']['id'])).status = 'closed'
    detail = client.get('/hiring/applications/'+selected['id'], headers=headers('cook'))
    assert detail.status_code == 200 and detail.json['application']['role']['status'] == 'closed'
    assert client.get('/hiring/applications/'+selected['id'], headers=headers('other')).status_code == 404
    assert client.get('/hiring/my-applications?cursor=invalid', headers=headers('cook')).status_code == 400


def test_unclear_attempt_is_reviewable_only_with_current_consent(db, client):
    from services.hiring_applications import sync_application
    with database.db_session() as session:
        session.add(CookProfile(user_id='cook', skill_verified=False))
        application = HiringApplication(role_posting_id=db.role, applicant_id='cook', answers={}, question_schema=[],
            consent_version='cookcredit-hiring-application-v1', status='assessment_processing', attempt_limit=3)
        session.add(application); session.flush()
        unclear = SkillAttempt(user_id='cook', session_id='unclear-live', profile_id='wrist_motion', verification_state='INSUFFICIENT',
            metadata_={'source': 'cookcredit-skill-live', 'recording_path': 'skill_videos/cook/unclear.webm', 'recording_generation': '987'})
        session.add(unclear); session.flush()
        from datetime import datetime, timedelta, timezone
        handoff = HiringAssessmentSession(application_id=application.id, applicant_id='cook', slot=1,
            attempt_id=unclear.id, status='processing', expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
        session.add(handoff); session.flush()
        sync_application(session, application)
        assert session.query(AssessmentShare).count() == 0
        application.consent_version = hiring.APPLICATION_CONSENT_VERSION
        sync_application(session, application)
        assert session.query(AssessmentShare).count() == 1
        aid = str(application.id)
    report = client.get('/business/candidate/cook/report', headers=headers('employer'))
    assert report.status_code == 200
    assert report.json['assessment']['deviceEstimates']['serverVerified'] is False
    assert report.json['assessment']['score'] is None
    assert client.get('/business/candidate/cook/video', headers=headers('employer')).status_code == 200
    assert client.get('/business/candidate/cook/video', headers=headers('other')).status_code == 403
    roster = client.get('/business/candidates', headers=headers('employer'))
    assert roster.json['candidates'][0]['verifiedScore'] is None
    assert client.post('/hiring/applications/'+aid+'/withdraw', headers=headers('cook')).status_code == 200
    assert client.get('/business/candidate/cook/video', headers=headers('employer')).status_code == 403
    assert client.get('/business/candidates', headers=headers('employer')).json['candidates'] == []


def test_company_logo_upload_is_admin_scoped_and_remove_revokes_public_route(db, client, monkeypatch):
    from io import BytesIO
    import hashlib
    from PIL import Image
    saved = {}
    def store(org_id, data):
        digest = hashlib.sha256(data).hexdigest()
        saved[(org_id, digest)] = data
        return digest
    monkeypatch.setattr(business.company_branding, 'store_logo', store)
    monkeypatch.setattr(business.company_branding, 'read_logo', lambda org_id, digest: saved[(org_id, digest)])
    monkeypatch.setenv('PUBLIC_API_URL', 'https://api.example.test')
    def image():
        data = BytesIO()
        Image.new('RGB', (20, 10), 'orange').save(data, format='PNG')
        data.seek(0)
        return data
    for uid in ('viewer', 'cook'):
        denied = client.post('/business/integrations/logo', headers=headers(uid), data={'logo': (image(), 'logo.png')})
        assert denied.status_code == 403
    assert saved == {}
    uploaded = client.post('/business/integrations/logo', headers=headers('employer'), data={'logo': (image(), 'logo.png')})
    assert uploaded.status_code == 200
    url = uploaded.json['org']['branding']['logoUrl']
    assert str(db.org) in url and str(db.other_org) not in url
    path = url.split('https://api.example.test/api', 1)[1]
    public = client.get(path)
    assert public.status_code == 200 and public.mimetype == 'image/png'
    assert public.headers['X-Content-Type-Options'] == 'nosniff'
    assert client.get(path, headers={'If-None-Match': public.headers['ETag']}).status_code == 304
    assert client.get(path.replace(str(db.org), str(db.other_org))).status_code == 404
    assert client.delete('/business/integrations/logo', headers=headers('other')).status_code == 200
    assert client.get(path).status_code == 200
    assert client.delete('/business/integrations/logo', headers=headers('viewer')).status_code == 403
    removed = client.delete('/business/integrations/logo', headers=headers('employer'))
    assert removed.status_code == 200 and removed.json['org']['branding']['logoUrl'] is None
    assert client.get(path).status_code == 404


def test_five_open_roles_preserves_scope_and_drafts(client, db, monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '1')
    body = {'title': 'Internal quota test', 'locationLabel': 'Test kitchen'}
    assert client.post('/business/roles', json=body, headers=headers('viewer')).status_code == 403
    # One role already exists in each of the two isolated workspaces.
    for _ in range(4):
        assert client.post('/business/roles', json=body, headers=headers('employer')).status_code == 201
    blocked = client.post('/business/roles', json=body, headers=headers('employer'))
    assert blocked.status_code == 409
    assert blocked.json['openRoleLimit'] == 5 and not blocked.json['upgradeRequired']
    assert client.post('/business/roles', json={**body, 'status': 'draft'}, headers=headers('employer')).status_code == 201
    assert client.post('/business/roles', json=body, headers=headers('other')).status_code == 201
    with database.db_session() as session:
        assert session.get(Org, db.org).plan == 'trial'
        assert session.query(RolePosting).filter_by(org_id=db.org, status='open').count() == 5


def test_normal_trial_retains_one_open_role(client, db, monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '0')
    result = client.post('/business/roles', json={'title': 'Test', 'locationLabel': 'Test'}, headers=headers('employer'))
    assert result.status_code == 409 and result.json['openRoleLimit'] == 1


def test_simultaneous_role_publications_cannot_exceed_five(client, db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '1')
    with database.db_session() as session:
        session.add_all([RolePosting(org_id=db.org, title='Test', status='open') for _ in range(3)])
    def publish(_):
        with client.application.test_client() as caller:
            return caller.post('/business/roles', json={'title': 'Concurrent test', 'locationLabel': 'Test'}, headers=headers('employer')).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(publish, range(2)))
    assert sorted(statuses) == [201, 409]
    with database.db_session() as session:
        assert session.query(RolePosting).filter_by(org_id=db.org, status='open').count() == 5


def apply_with_cv(client, url, *, headers, json):
    import io
    import json as json_module
    return client.post(url, headers=headers, data={
        'application': json_module.dumps(json),
        'cv': (io.BytesIO(b'%PDF-1.4\nTest CV\n%%EOF'), 'cv.pdf'),
    })

def test_cv_required_and_download_isolation(client, db, monkeypatch):
    body={'fullName':'New Applicant', 'acceptedEvidenceShare':True,
          'consentVersion':hiring.APPLICATION_CONSENT_VERSION,'answers':{}}
    missing=client.post(f'/hiring/roles/{db.role}/apply', headers=headers('cook'), json=body)
    assert missing.status_code==400 and 'CV' in missing.json['error']
    invalid=apply_with_cv(client,f'/hiring/roles/{db.role}/apply',headers=headers('cook'),json={**body,'fullName':'  '})
    assert invalid.status_code==400
    applied=apply_with_cv(client,f'/hiring/roles/{db.role}/apply',headers=headers('cook'),json=body)
    assert applied.status_code==201
    aid=applied.json['application']['id']
    assert applied.json['application']['hasCv'] is True
    assert applied.json['application']['applicantName']=='New Applicant'
    # Retry reuses the accepted application without requiring another upload.
    retry=client.post(f'/hiring/roles/{db.role}/apply',headers=headers('cook'),json=body)
    assert retry.json['application']['id']==aid
    downloads=[]
    monkeypatch.setattr(hiring.hiring_cv,'download_cv',lambda *args: downloads.append(args) or b'%PDF-1.4\nCV\n%%EOF')
    url=f'/hiring/applications/{aid}/cv'
    for identity in ('other','viewer'):
        assert client.get(url,headers=headers(identity)).status_code==404
    assert downloads==[]
    for identity in ('cook','employer'):
        response=client.get(url,headers=headers(identity))
        assert response.status_code==200
        assert response.headers['Cache-Control']=='private, no-store'
        assert response.headers['Content-Disposition'].startswith('attachment;')
        assert response.headers['Content-Security-Policy'].startswith('sandbox;')
    assert client.post(f'/hiring/applications/{aid}/withdraw',headers=headers('cook')).status_code==200
    assert client.get(url,headers=headers('employer')).status_code==404
    assert client.get(url,headers=headers('cook')).status_code==200
    listed=client.get(f'/hiring/roles/{db.role}/applications',headers=headers('employer'))
    assert listed.json['applications'][0]['hasCv'] is False


def test_cv_storage_failure_does_not_create_application(client,db,monkeypatch):
    def fail(*args): raise RuntimeError('storage unavailable')
    monkeypatch.setattr(hiring.hiring_cv,'store_cv',fail)
    result=apply_with_cv(client,f'/hiring/roles/{db.role}/apply',headers=headers('cook'),json={
        'fullName':'Applicant','acceptedEvidenceShare':True,'consentVersion':hiring.APPLICATION_CONSENT_VERSION})
    assert result.status_code==503
    with database.db_session() as session:
        assert session.query(HiringApplication).count()==0


def test_application_review_cv_privacy_revision_and_withdrawal(db, client, monkeypatch):
    from services import hiring_access
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'test')
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '0')
    monkeypatch.setattr(hiring_access, 'enabled', lambda: False)
    with database.db_session() as session:
        application = HiringApplication(role_posting_id=db.role, applicant_id='cook',
            answers={'experience':'Two years'}, question_schema=[{'id':'experience','label':'Experience'}],
            applicant_details={'name':'Applicant Name','cv':{'path':'private-test-cv'}},
            consent_version=hiring.APPLICATION_CONSENT_VERSION, status='assessment_required', attempt_limit=3)
        session.add(application); session.flush(); aid=str(application.id)
        session.add(PipelineCard(role_posting_id=db.role,cook_id='cook',stage='assessing'))
    url=f'/hiring/applications/{aid}'
    listing='/hiring/candidates/cook/applications'
    result=client.get(listing,headers=headers('employer'))
    assert result.status_code==200 and result.json['canReview'] is True
    assert result.json['applications'][0]['hasCv'] is True
    assert result.json['applications'][0]['applicantName']=='Applicant Name'
    monkeypatch.setattr(hiring.hiring_cv,'download_cv',lambda *a:b'%PDF-disposable-test')
    assert client.get(url+'/cv',headers=headers('employer')).data==b'%PDF-disposable-test'
    assert client.get(url+'/cv',headers=headers('other')).status_code==404
    assert client.get(listing,headers=headers('other')).json['applications']==[]
    assert client.get(listing,headers=headers('cook')).status_code==404
    assert client.get(listing,headers=headers('viewer')).status_code==404
    draft={'status':'shortlisted','notes':'INTERNAL SECRET','message':'We would like to speak with you.','publish':False,'revision':None}
    for uid in ('cook','other','viewer'):
        assert client.post(url+'/review',json=draft,headers=headers(uid)).status_code==404
    saved=client.post(url+'/review',json=draft,headers=headers('employer'))
    assert saved.status_code==200 and saved.json['employerUpdate'] is None
    assert client.get('/business/shortlist', headers=headers('employer')).json['cookIds'] == ['cook']
    board = client.get(f'/business/role/{db.role}', headers=headers('employer')).json['pipeline']
    assert board == [{'cookId': 'cook', 'stage': 'shortlisted', 'hasVideo': False}]
    revision=saved.json['review']['revision']
    assert saved.json['review']['reviewerName']=='employer'
    applicant=client.get(url,headers=headers('cook'))
    assert applicant.status_code==200 and applicant.json['application']['employerUpdate'] is None
    assert 'INTERNAL SECRET' not in applicant.get_data(as_text=True)
    assert client.post(url+'/review',json=draft,headers=headers('employer')).status_code==409
    published=client.post(url+'/review',json={**draft,'revision':revision,'publish':True},headers=headers('employer'))
    assert published.status_code==200
    public=client.get(url,headers=headers('cook')).json['application']['employerUpdate']
    assert set(public)=={'status','message','updatedAt'} and public['status']=='shortlisted'
    assert 'INTERNAL SECRET' not in str(public)
    revision=published.json['review']['revision']
    private=client.post(url+'/review',json={**draft,'status':'hired','revision':revision},headers=headers('employer'))
    assert private.status_code==200
    assert client.get(url,headers=headers('cook')).json['application']['employerUpdate']['status']=='shortlisted'
    with database.db_session() as session:
        assert session.query(PipelineCard).filter_by(role_posting_id=db.role,cook_id='cook').one().stage=='hired'
        before=session.query(HiringApplicationEvent).filter_by(application_id=aid).count()
    replay=client.post(url+'/review',json={**draft,'status':'hired','revision':private.json['review']['revision']},headers=headers('employer'))
    assert replay.status_code==200
    with database.db_session() as session:
        assert session.query(HiringApplicationEvent).filter_by(application_id=aid).count()==before
    monkeypatch.setattr(business, '_shared_candidate', lambda *a: True)
    assert client.post(f'/business/role/{db.role}/stage',headers=headers('employer'),json={'cookId':'cook','stage':'contacted'}).status_code==200
    board_review=client.get(listing,headers=headers('employer')).json['applications'][0]
    assert board_review['review']['status']=='contacted'
    assert board_review['employerUpdate']['status']=='shortlisted'
    assert client.post(url+'/review',json={**draft,'revision':private.json['review']['revision']},headers=headers('employer')).status_code==409
    monkeypatch.setattr(hiring_access,'enabled',lambda:True)
    monkeypatch.setattr(hiring_access,'access_allowed',lambda *a:False)
    # Shared authorization rejects a revoked employer before the route executes.
    for denied in (client.get(listing,headers=headers('employer')),
                   client.post(url+'/review',json=draft,headers=headers('employer'))):
        assert denied.status_code==403 and denied.json['code']=='staging_access_denied'
    assert client.get(url+'/cv',headers=headers('employer')).status_code==404
    monkeypatch.setattr(hiring_access,'enabled',lambda:False)
    assert client.post(url+'/withdraw',headers=headers('cook')).status_code==200
    assert client.get(listing,headers=headers('employer')).json['applications']==[]
    assert client.get(url+'/cv',headers=headers('employer')).status_code==404
    assert client.post(url+'/review',json=draft,headers=headers('employer')).status_code==404


def test_price_versions_preserve_subscription_limits_and_reject_stale_drafts(db):
    from models.billing_catalog import HiringPrice
    from services.billing_catalog import publish_price, price_for_subscription
    with database.db_session() as session:
        old = HiringPrice(plan='integration', interval='month', currency='usd', amount=29900,
                          limits={'seats': 15, 'openRoles': 25, 'monthlyRequests': 1000},
                          state='published', active=True, stripe_price_id='price_original', created_by='owner')
        session.add(old); session.flush(); old_id = old.id
        drafts = [HiringPrice(plan='integration', interval='month', currency='usd', amount=34900,
                              limits={'seats': 20, 'openRoles': 30, 'monthlyRequests': 1500},
                              previous_id=old_id, created_by='owner') for _ in range(2)]
        session.add_all(drafts); session.flush(); first, stale = [row.id for row in drafts]
    assert publish_price(first, create=lambda _: 'price_revised')['active'] is True
    assert publish_price(first, create=lambda _: pytest.fail('must reuse published price'))['active'] is True
    with pytest.raises(ValueError, match='current price changed'):
        publish_price(stale, create=lambda _: 'price_stale')
    with pytest.raises(ValueError, match='new draft'):
        publish_price(old_id, create=lambda _: pytest.fail('must not republish history'))
    with database.db_session() as session:
        org = session.get(Org, db.org)
        stripe_routes._sync_subscription(org, {'id': 'sub_original', 'customer': 'cus_original',
            'status': 'active', 'items': {'data': [{'price': {'id': 'price_original'}}]}})
        assert org.plan == 'integration'
        assert org.subscription_limits == {'seats': 15, 'openRoles': 25, 'monthlyRequests': 1000}
        assert price_for_subscription(session, 'price_original').active is False
        assert session.query(HiringPrice).filter_by(active=True).count() == 1


def test_owner_pricing_requires_verified_owner_and_valid_limits(db, client, monkeypatch):
    from routes.hiring_access import access_bp
    client.application.register_blueprint(access_bp, url_prefix='/access')
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    from services.billing_catalog import DEFAULTS
    monkeypatch.setattr(auth, '_verify_token', lambda token: {
        'uid': token, 'email': 'eassefa@cookcredit.com' if token in ('owner', 'unverified') else token+'@example.test',
        'email_verified': token != 'unverified'})
    for uid in ('viewer', 'employer', 'unverified'):
        assert client.get('/access/owner/pricing', headers=headers(uid)).status_code == 403
        assert client.post('/access/owner/pricing', headers=headers(uid), json=DEFAULTS[0]).status_code == 403
    response = client.post('/access/owner/pricing', headers=headers('owner'), json=DEFAULTS[0])
    assert response.status_code == 201
    assert response.json['price']['state'] == 'draft'
    assert response.json['price']['active'] is False
    assert client.post('/access/owner/pricing', headers=headers('owner'), json=DEFAULTS[0] | {'amount': True}).status_code == 400
    listing = client.get('/access/owner/pricing', headers=headers('owner'))
    assert len(listing.json['prices']) == 1
    assert 'stripe_price_id' not in listing.json['prices'][0]


def test_shortlist_pending_applicant_persists_without_unlocking_video(db, client):
    with database.db_session() as session:
        application = HiringApplication(role_posting_id=db.role, applicant_id='cook',
            consent_version=hiring.APPLICATION_CONSENT_VERSION, status='assessment_required',
            applicant_details={'name': 'Pending Applicant'}, attempt_limit=3)
        session.add(application); session.flush(); aid=application.id
    endpoint='/business/shortlist'
    assert client.post(endpoint, json={'cookId':'cook'}, headers=headers('other')).status_code == 403
    assert client.post(endpoint, json={'cookId':'cook'}, headers=headers('viewer')).status_code == 403
    saved=client.post(endpoint, json={'cookId':'cook'}, headers=headers('employer'))
    assert saved.status_code == 200 and saved.json['shortlisted'] is True
    listing=client.get(endpoint, headers=headers('employer')).json
    assert listing['cookIds'] == ['cook']
    assert listing['candidates'][0]['name'] == 'Pending Applicant'
    assert listing['candidates'][0]['hasVideo'] is False
    assert client.get('/business/candidate/cook/video', headers=headers('employer')).status_code == 403
    assert client.post(endpoint, json={'cookId':'cook'}, headers=headers('employer')).json['shortlisted'] is False
    assert client.get(endpoint, headers=headers('employer')).json['cookIds'] == []
    client.post(endpoint, json={'cookId':'cook'}, headers=headers('employer'))
    with database.db_session() as session:
        session.get(HiringApplication, aid).status='withdrawn'
    assert client.get(endpoint, headers=headers('employer')).json['cookIds'] == []
    assert client.post(endpoint, json={'cookId':'cook'}, headers=headers('employer')).status_code == 403
