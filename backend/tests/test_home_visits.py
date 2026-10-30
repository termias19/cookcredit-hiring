"""Home workflow/security acceptance in disposable local PostgreSQL schemas.

PostGIS is used when installed (as in CI). On local PostgreSQL without PostGIS,
only the two unused spatial columns are omitted from the core table fixture;
all Home DDL, constraints, transactions, locks and API queries remain real SQL.
No cloud/database URL from application configuration is accepted by these tests.
"""
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text, select, insert, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from middleware import auth
from models import User, CookProfile, Booking
from models.home_service import HomeVisit, HomeEvent, HomeCommand, HomeHelperPermission
from services import database, home_visits as visits
from services import hiring_access
from home_app import create_app, database_url


@pytest.fixture
def home_db(monkeypatch):
    url = os.getenv('HOME_TEST_DATABASE_URL') or os.getenv('HIRING_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Explicit disposable local PostgreSQL required')
    parsed = make_url(url)
    assert parsed.host in ('127.0.0.1', 'localhost') and parsed.username == 'cookcredit_test'
    assert parsed.database == 'cookcredit_test'
    schema = 'home_test_' + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA {schema}')
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public -c lock_timeout=5000 -c statement_timeout=10000'},
                           pool_size=10, max_overflow=0)
    try:
        with engine.begin() as conn:
            spatial = conn.execute(text("SELECT to_regtype('geography') IS NOT NULL")).scalar()
            for table in (User.__table__, CookProfile.__table__, Booking.__table__):
                ddl = str(CreateTable(table).compile(engine))
                if not spatial:
                    ddl = re.sub(r'^\s*(?:base_location|eater_location)\s+geography\([^\n]+\),\s*\n', '', ddl, flags=re.I | re.M)
                conn.exec_driver_sql(ddl)
            sql = (Path(__file__).parents[1] / 'home/migrations/001_booking_workflow.sql').read_text()
            conn.exec_driver_sql(sql)
            conn.exec_driver_sql(sql)  # Replay is safe; it never applies in Hiring migrations.
        monkeypatch.setattr(database, 'engine', engine)
        monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA {schema} CASCADE')
        admin.dispose()


@pytest.fixture
def app(home_db, monkeypatch):
    monkeypatch.setenv('HOME_OWNER_EMAILS', 'owner@example.test')
    monkeypatch.setenv('HOME_OPERATOR_EMAILS', 'operator@example.test')
    # Home identity must work even when Hiring would deny employer access.
    monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '1')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setattr(hiring_access, 'employer_access_allowed', lambda *a, **kw: pytest.fail('Home must not apply employer access policy'))
    monkeypatch.setattr(auth, '_verify_token', lambda token: {'uid': token,
        'email': token + '@example.test', 'email_verified': token != 'unverified'})
    return create_app({'TESTING': True, 'HOME_ENABLED': True, 'RATELIMIT_ENABLED': False})


def headers(uid='customer', key=None):
    result = {'Authorization': 'Bearer ' + uid}
    if key:
        result['Idempotency-Key'] = key
    return result


def payload(service='both'):
    return {'service': service, 'date': (datetime.now(timezone.utc) + timedelta(days=3)).date().isoformat(),
        'time': '10:00', 'durationMinutes': 150, 'address': 'Synthetic home address',
        'instructions': {'preferences': ['allergies', 'fragrance_free'], 'cleaningTasks': ['kitchen'] if service != 'cooking' else [],
            'visitNotes': 'Synthetic sensitive visit instruction'},
        'consent': {'version': visits.CONSENT_VERSION, 'shareWithAssignedHelper': True}}


def create(client, body=None, key=None, uid='customer'):
    return client.post('/api/home/visits', json=body or payload(), headers=headers(uid, key or uuid.uuid4().hex))


def change(client, visit, action, uid='owner', **extra):
    return client.post(f"/api/home/visits/{visit['id']}/actions", headers=headers(uid, uuid.uuid4().hex),
        json={'action': action, 'version': visit['version'], **extra})


def seed_helper(client, uid='helper', *, cooking=True, cleaning=True, approved=True):
    assert client.get('/api/home/me', headers=headers(uid)).status_code == 200
    with database.db_session() as session:
        session.execute(insert(CookProfile.__table__).values(user_id=uid, approved=approved))
    return client.put(f'/api/home/helpers/{uid}/permission', headers=headers('owner', uuid.uuid4().hex),
                      json={'enabled': True, 'cooking': cooking, 'cleaning': cleaning})


def test_default_is_off_and_exposes_no_hiring_routes(monkeypatch):
    monkeypatch.delenv('HOME_SERVICES_ENABLED', raising=False)
    app = create_app({'TESTING': True})
    assert app.test_client().get('/api/home/health').json['status'] == 'disabled'
    assert app.test_client().post('/api/home/visits').status_code == 503
    assert 'business' not in app.blueprints and 'auth' not in app.blueprints


@pytest.mark.parametrize('url', [
    'postgresql://cookcredit_home_app@localhost/cookcredit_hiring',
    'postgresql://postgres@localhost/cookcredit_home_staging',
    'sqlite:///cookcredit_home_staging', '',
])
def test_home_refuses_other_product_database(monkeypatch, url):
    monkeypatch.setenv('COOKCREDIT_PRODUCT', 'home-services')
    monkeypatch.setenv('HOME_DATABASE_URL', url)
    with pytest.raises(RuntimeError):
        database_url()


def test_home_accepts_explicit_dedicated_database(monkeypatch):
    monkeypatch.setenv('COOKCREDIT_PRODUCT', 'home-services')
    url = 'postgresql://cookcredit_home_app@localhost/cookcredit_home_staging'
    monkeypatch.setenv('HOME_DATABASE_URL', url)
    assert database_url() == url


def test_identity_verification_and_cross_customer_privacy(app):
    client = app.test_client()
    assert client.post('/api/home/visits', json=payload()).status_code == 401
    assert create(client, uid='unverified').status_code == 403
    created = create(client)
    assert created.status_code == 201
    path = '/api/home/visits/' + created.json['id']
    assert client.get(path, headers=headers('stranger')).status_code == 404
    assert client.get('/api/home/visits', headers=headers('stranger')).json['visits'] == []
    assert client.get(path, headers=headers()).json['instructions']['visitNotes'] == payload()['instructions']['visitNotes']
    listing = client.get('/api/home/visits', headers=headers()).json
    assert len(listing['visits']) == 1 and 'instructions' not in listing['visits'][0]
    assert 'address' not in listing['visits'][0]
    assert client.get(path + '/activity', headers=headers()).status_code == 403


def test_review_assignment_capability_accept_and_audit(app):
    client = app.test_client()
    row = create(client).json
    assert seed_helper(client, cleaning=False).status_code == 200
    assert change(client, row, 'assign', helperId='helper').status_code == 409
    assert change(client, row, 'review', uid='customer').status_code == 403
    reviewed = change(client, row, 'review')
    assert reviewed.status_code == 200
    row = reviewed.json
    assert change(client, row, 'assign', helperId='helper').json['code'] == 'helper_ineligible'
    client.put('/api/home/helpers/helper/permission', headers=headers('owner', uuid.uuid4().hex),
               json={'enabled': True, 'cooking': True, 'cleaning': True})
    assigned = change(client, row, 'assign', helperId='helper')
    assert assigned.status_code == 200
    row = assigned.json
    assert client.get('/api/home/visits/' + row['id'], headers=headers('helper')).status_code == 200
    assert len(client.get('/api/home/visits', headers=headers('helper')).json['visits']) == 1
    assert change(client, row, 'accept', uid='owner').status_code == 403
    accepted = change(client, row, 'accept', uid='helper')
    assert accepted.status_code == 200 and accepted.json['status'] == 'accepted'
    # No backdoor to mark an uncharged visit paid, started, completed or paid out.
    for action in ('pay', 'start', 'finish', 'confirm', 'payout'):
        assert change(client, accepted.json, action).status_code == 400
    events = client.get('/api/home/visits/' + row['id'] + '/activity', headers=headers('operator')).json['events']
    assert [e['action'] for e in events] == ['visit_requested', 'review', 'assign', 'accept']
    assert payload()['instructions']['visitNotes'] not in str(events)


@pytest.mark.parametrize('approved,cooking,cleaning', [(False, True, True), (True, False, True), (True, True, False)])
def test_cooking_and_cleaning_have_explicit_permissions(app, approved, cooking, cleaning):
    client = app.test_client()
    row = change(client, create(client).json, 'review').json
    seed_helper(client, approved=approved, cooking=cooking, cleaning=cleaning)
    assert change(client, row, 'assign', helperId='helper').json['code'] == 'helper_ineligible'


def test_revoked_helper_immediately_loses_list_detail_and_accept(app):
    client = app.test_client()
    seed_helper(client)
    row = change(client, create(client).json, 'review').json
    row = change(client, row, 'assign', helperId='helper').json
    denied = client.put('/api/home/helpers/helper/permission', headers=headers('operator', uuid.uuid4().hex),
        json={'enabled': False, 'cooking': True, 'cleaning': True})
    assert denied.status_code == 403
    client.put('/api/home/helpers/helper/permission', headers=headers('owner', uuid.uuid4().hex),
        json={'enabled': False, 'cooking': True, 'cleaning': True})
    assert client.get('/api/home/visits/' + row['id'], headers=headers('helper')).status_code == 404
    assert client.get('/api/home/visits', headers=headers('helper')).json['visits'] == []
    assert change(client, row, 'accept', uid='helper').status_code == 404


def test_concurrent_retries_create_one_booking_and_one_event(app):
    key, body = uuid.uuid4().hex, payload()
    def send(_):
        with app.test_client() as client:
            response = create(client, body, key)
            return response.status_code, response.json
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(send, range(6)))
    assert {status for status, _ in results} == {201}
    assert len({result['id'] for _, result in results}) == 1
    with database.db_session() as session:
        assert session.query(HomeVisit).count() == session.query(HomeEvent).count() == session.query(HomeCommand).count() == 1
    body['durationMinutes'] = 180
    assert create(app.test_client(), body, key).json['code'] == 'idempotency_conflict'


def test_concurrent_stale_changes_cannot_overwrite(app):
    row = create(app.test_client()).json
    def review(uid):
        with app.test_client() as client:
            return change(client, row, 'review', uid=uid).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(review, ['owner', 'operator']))
    assert sorted(statuses) == [200, 409]
    with database.db_session() as session:
        assert session.query(HomeEvent).count() == 2


def test_issue_hold_resolution_cancellation_and_stale_screen(app):
    client = app.test_client()
    row = create(client).json
    held = change(client, row, 'report_issue', uid='customer').json
    assert change(client, held, 'review').json['code'] == 'issue_open'
    assert change(client, held, 'resolve_issue', uid='customer').status_code == 403
    resolved = change(client, held, 'resolve_issue').json
    assert change(client, row, 'cancel', uid='customer').json['code'] == 'stale_version'
    cancelled = change(client, resolved, 'cancel', uid='customer')
    assert cancelled.status_code == 200 and cancelled.json['status'] == 'cancelled'
    assert change(client, cancelled.json, 'review').json['code'] == 'visit_closed'


def test_atomic_rollback_and_safe_error_logging(app, monkeypatch, capsys):
    def broken(*args, **kwargs):
        raise RuntimeError('private@example.test sensitive instruction')
    monkeypatch.setattr(visits, 'event', broken)
    response = create(app.test_client())
    assert response.status_code == 503 and response.json['reference'] == response.headers['X-Request-ID']
    output = capsys.readouterr().out
    assert 'home_unhandled_error' in output and 'RuntimeError' in output
    assert 'private@example.test' not in output and 'sensitive instruction' not in output
    with database.db_session() as session:
        assert session.query(HomeVisit).count() == session.query(HomeCommand).count() == 0
        assert session.execute(select(func.count(Booking.id))).scalar() == 0


@pytest.mark.parametrize('mutation', ['consent', 'roles', 'bad_date', 'float_duration', 'extra_notes', 'nan'])
def test_rejects_untrusted_or_unconsented_request(app, mutation):
    body = payload()
    if mutation == 'consent': body['consent']['shareWithAssignedHelper'] = False
    elif mutation == 'roles': body['roles'] = ['admin']
    elif mutation == 'bad_date': body['date'] = 'garbage'
    elif mutation == 'float_duration': body['durationMinutes'] = 150.5
    elif mutation == 'extra_notes': body['instructions']['diagnosis'] = 'not collected'
    elif mutation == 'nan': body['durationMinutes'] = float('nan')
    assert create(app.test_client(), body).status_code == 400


def test_missing_key_and_oversized_request_rejected(app):
    client = app.test_client()
    assert client.post('/api/home/visits', json=payload(), headers=headers()).status_code == 400
    assert client.post('/api/home/visits', data='x' * 17000,
        content_type='application/json', headers=headers('customer', uuid.uuid4().hex)).status_code == 413


def test_keyset_pagination_is_bounded_and_excludes_private_details(app):
    client = app.test_client()
    for _ in range(52):
        assert create(client).status_code == 201
    first = client.get('/api/home/visits', headers=headers()).json
    assert len(first['visits']) == 50 and first['nextCursor']
    second = client.get('/api/home/visits', query_string={'cursor': first['nextCursor']}, headers=headers()).json
    assert len(second['visits']) == 2 and second['nextCursor'] is None
    assert len({v['id'] for v in first['visits'] + second['visits']}) == 52
    assert 'Synthetic home address' not in str(first) and 'Synthetic sensitive' not in str(first)
    assert client.get('/api/home/visits?cursor=bad', headers=headers()).status_code == 400


def test_cleaning_permission_does_not_require_cooking_approval(app):
    client = app.test_client()
    seed_helper(client, cooking=False, cleaning=True, approved=False)
    row = change(client, create(client, payload('cleaning')).json, 'review').json
    assigned = change(client, row, 'assign', helperId='helper')
    assert assigned.status_code == 200
    assert len(client.get('/api/home/visits', headers=headers('helper')).json['visits']) == 1
    assert change(client, assigned.json, 'accept', uid='helper').status_code == 200


def test_migration_not_discovered_by_hiring_runner():
    from migrations.run_migrations import discover
    backend = Path(__file__).parents[1].resolve()
    assert all(Path(path).resolve().parent == backend / 'migrations' for _, path in discover())
