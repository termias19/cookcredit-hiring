"""Real DB coverage for tenant isolation, last-admin protection and activity."""
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
from models import OrgMembership, Org, OrgInvitation, User
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from models.business import WorkspaceActivity
from services import database
from tests.test_hiring_postgres import client, headers

pytestmark = pytest.mark.skipif(not os.environ.get('HIRING_TEST_DATABASE_URL'), reason='isolated PostgreSQL required')

@pytest.fixture
def db(monkeypatch):
    # This feature has no spatial dependency; exercise its actual tables and SQL
    # without requiring the unrelated marketplace's PostGIS extension locally.
    url = os.environ['HIRING_TEST_DATABASE_URL']
    parsed = make_url(url)
    if parsed.host not in ('127.0.0.1', 'localhost') or parsed.username != 'cookcredit_test':
        pytest.fail('Only the dedicated localhost test database is allowed')
    schema = 'workspace_test_' + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public'})
    try:
        for model in (User, Org, OrgMembership, OrgInvitation):
            model.__table__.create(engine)
        with engine.begin() as conn:
            sql = (Path(__file__).parents[1] / 'migrations/033_workspace_activity.sql').read_text()
            conn.exec_driver_sql(sql); conn.exec_driver_sql(sql)
        monkeypatch.setattr(database, 'engine', engine)
        monkeypatch.setattr(database, 'SessionLocal', sessionmaker(bind=engine, expire_on_commit=False))
        monkeypatch.setenv('HIRING_ACCESS_APPROVALS_ENABLED', '0')
        monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'development')
        ids = SimpleNamespace(org=uuid.uuid4(), other_org=uuid.uuid4())
        with database.db_session() as session:
            for uid in ('employer', 'viewer', 'other'):
                session.add(User(id=uid, email=uid+'@example.test', name=uid, roles=['business']))
            session.flush()
            session.add_all([Org(id=ids.org, name='Kitchen'), Org(id=ids.other_org, name='Other')]); session.flush()
            session.add_all([OrgMembership(org_id=ids.org, user_id='employer', seat_role='admin'),
                OrgMembership(org_id=ids.org, user_id='viewer', seat_role='viewer'),
                OrgMembership(org_id=ids.other_org, user_id='other', seat_role='admin')])
        yield ids
    finally:
        engine.dispose()
        with admin.begin() as conn: conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()

def member(client, user):
    return next(row['id'] for row in client.get('/business/team', headers=headers('employer')).json['members'] if row['userId'] == user)

def test_last_admin_cannot_remove_or_demote_self(client):
    target = '/business/team/members/' + member(client, 'employer')
    assert client.delete(target, headers=headers('employer')).status_code == 409
    assert client.patch(target, headers=headers('employer'), json={'seatRole':'viewer'}).status_code == 409
    assert client.get('/business/activity', headers=headers('employer')).json['events'] == []

def test_invalid_role_and_failed_audit_never_change_membership(client, monkeypatch):
    from routes import business
    target = '/business/team/members/' + member(client, 'viewer')
    for body in [['admin'], {'seatRole':'owner'}, {'seatRole':'admin','orgId':'other'}]:
        assert client.patch(target, headers=headers('employer'), json=body).status_code == 400
    def fail(*args, **kwargs): raise RuntimeError('audit storage failed')
    monkeypatch.setattr(business, 'record_activity', fail)
    with pytest.raises(RuntimeError):
        client.patch(target, headers=headers('employer'), json={'seatRole':'admin'})
    assert client.get('/business/activity', headers=headers('viewer')).status_code == 403
    assert client.delete('/business/activity', headers=headers('employer')).status_code == 405

def test_tenant_isolation_and_immediate_permission_change(client):
    target = '/business/team/members/' + member(client, 'viewer')
    assert client.patch(target, headers=headers('other'), json={'seatRole':'admin'}).status_code == 404
    assert client.patch(target, headers=headers('viewer'), json={'seatRole':'admin'}).status_code == 403
    assert client.get('/business/activity', headers=headers('viewer')).status_code == 403
    assert client.patch(target, headers=headers('employer'), json={'seatRole':'admin'}).status_code == 200
    assert client.get('/business/activity', headers=headers('viewer')).status_code == 200
    assert client.patch(target, headers=headers('employer'), json={'seatRole':'viewer'}).status_code == 200
    assert client.get('/business/activity', headers=headers('viewer')).status_code == 403
    assert client.delete(target, headers=headers('employer')).status_code == 200
    assert client.get('/business/roles', headers=headers('viewer')).status_code == 403
    assert client.get('/business/activity', headers=headers('other')).json['events'] == []
    events = client.get('/business/activity', headers=headers('employer')).json['events']
    assert len(events) == 3
    assert events[0]['action'] == 'member.removed'
    assert all(row['actorId'] == 'employer' for row in events)

def test_concurrent_admin_demotions_leave_one_admin(client, db):
    first = '/business/team/members/' + member(client, 'employer')
    second = '/business/team/members/' + member(client, 'viewer')
    assert client.patch(second, headers=headers('employer'), json={'seatRole':'admin'}).status_code == 200
    def demote(args):
        uid, target = args
        with client.application.test_client() as other_client:
            return other_client.patch(target, headers=headers(uid), json={'seatRole':'viewer'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(demote, [('employer', first), ('viewer', second)]))
    assert sorted(statuses) == [200, 409]
    with database.db_session() as session:
        assert session.query(OrgMembership).filter_by(org_id=db.org, seat_role='admin').count() == 1

def test_activity_cursor_is_company_bound_and_does_not_skip_equal_timestamps(client, db):
    with database.db_session() as session:
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc)
        for index in range(55):
            session.add(WorkspaceActivity(org_id=db.org, actor_id='employer', event_type='test', target_id=str(index), created_at=stamp))
        other = WorkspaceActivity(org_id=db.other_org, actor_id='other', event_type='test', target_id='private')
        session.add(other); session.flush(); other_id = str(other.id)
    first = client.get('/business/activity', headers=headers('employer')).json
    second = client.get('/business/activity?before='+first['nextCursor'], headers=headers('employer')).json
    assert len(first['events']) == 50 and len(second['events']) == 5
    assert len({row['id'] for row in first['events'] + second['events']}) == 55
    assert second['nextCursor'] is None
    assert client.get('/business/activity?before='+other_id, headers=headers('employer')).status_code == 400
