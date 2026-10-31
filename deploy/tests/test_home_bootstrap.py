"""Reject other product databases before an administrator connection is opened."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import URL

spec=importlib.util.spec_from_file_location('home_bootstrap',Path(__file__).parents[2]/'backend/scripts/bootstrap_home_staging_db.py')
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)


@pytest.mark.parametrize('change',[
    {'database':'cookcredit_hiring_staging'}, {'database':'cookcredit_home_prod'},
    {'username':'postgres'}, {'host':'unexpected.example'},
    {'query':{'host':'/cloudsql/toqto-prod:us-central1:unrelated'}},
    {'query':{'host':'/cloudsql/'+bootstrap.CONNECTION,'options':'-c role=postgres'}},
])
def test_home_target_rejects_wrong_database_role_or_socket(monkeypatch,change):
    url=URL.create('postgresql+psycopg2',username=bootstrap.ROLES[0],password='synthetic-only',
        database=bootstrap.DATABASE,query={'host':'/cloudsql/'+bootstrap.CONNECTION}).set(**change)
    monkeypatch.setenv('HOME_DATABASE_URL',url.render_as_string(hide_password=False))
    with pytest.raises(RuntimeError):bootstrap.target('HOME_DATABASE_URL',bootstrap.ROLES[0])


@pytest.mark.parametrize('key,value',[
    ('HOME_STAGING_BOOTSTRAP','0'), ('COOKCREDIT_ENVIRONMENT','production'),
    ('CLOUD_SQL_CONNECTION','cookcredit-scoring:us-central1:cookcredit-hiring-db'),
    ('CLOUD_RUN_JOB','cc-unrelated-job'),
])
def test_admin_job_guard_precedes_all_database_operations(monkeypatch,key,value):
    for name,setting in {'HOME_STAGING_BOOTSTRAP':'1','COOKCREDIT_ENVIRONMENT':'staging',
        'CLOUD_SQL_CONNECTION':bootstrap.CONNECTION,'CLOUD_RUN_JOB':'cc-hiring-stg-migrate'}.items():
        monkeypatch.setenv(name,setting)
    monkeypatch.setenv(key,value)
    monkeypatch.setattr(bootstrap,'create_engine',lambda *a,**k:pytest.fail('Unauthorized connection attempted'))
    with pytest.raises(RuntimeError):bootstrap.main()


@pytest.mark.parametrize('already_member', [False, True])
@pytest.mark.parametrize('fail', [False, True])
def test_temporary_admin_membership_is_released_on_success_or_failure(already_member, fail):
    class Cursor:
        def __init__(self):
            self.calls=[]
        def execute(self, statement, parameters=None):
            self.calls.append(str(statement))
        def fetchone(self):
            return (already_member,)
    cursor=Cursor()
    if fail:
        with pytest.raises(RuntimeError):
            with bootstrap.migration_owner(cursor):
                raise RuntimeError('synthetic failure')
    else:
        with bootstrap.migration_owner(cursor):
            pass
    assert 'RESET ROLE' in cursor.calls
    grants=[q for q in cursor.calls if 'GRANT ' in q]
    revokes=[q for q in cursor.calls if 'REVOKE ' in q]
    assert len(grants)==len(revokes)==(0 if already_member else 1)
    assert all('CURRENT_USER' in q and 'cookcredit_home_migrator' in q for q in grants+revokes)


def test_managed_admin_retains_owner_access_until_schema_setup_finishes(monkeypatch):
    from contextlib import contextmanager
    membership={'active':False}
    class Cursor:
        statement=''
        def execute(self, statement, parameters=None):
            self.statement=str(statement)
            if 'GRANT ' in self.statement and 'CURRENT_USER' in self.statement:
                membership['active']=True
            elif 'REVOKE ' in self.statement and 'CURRENT_USER' in self.statement:
                membership['active']=False
        def fetchone(self):
            if 'max_connections' in self.statement:return (20,)
            if 'FROM pg_auth_members' in self.statement:return None
            if 'FROM pg_roles WHERE rolname' in self.statement:return (False,)*5+(bootstrap.MARKER,)
            if 'FROM pg_database' in self.statement:return (bootstrap.ROLES[0],bootstrap.MARKER)
            if 'pg_has_role' in self.statement:return (membership['active'],)
            raise AssertionError('Unexpected bootstrap read')
        def close(self):pass
    cursor=Cursor()
    class Driver:
        def cursor(self):return cursor
    class Connection:
        class Wrapper:
            driver_connection=Driver()
        connection=Wrapper()
        def exec_driver_sql(self, statement):
            assert membership['active'], 'Managed administrator lost Home owner access during setup'
    class Engine:
        @contextmanager
        def connect(self):yield Connection()
        @contextmanager
        def begin(self):
            # PUBLIC CONNECT has been revoked; managed postgres needs its
            # temporary Home owner membership for this second connection.
            assert membership['active']
            yield Connection()
        def dispose(self):pass
    for name,value in {'HOME_STAGING_BOOTSTRAP':'1','COOKCREDIT_ENVIRONMENT':'staging',
        'CLOUD_SQL_CONNECTION':bootstrap.CONNECTION,'CLOUD_RUN_JOB':'cc-hiring-stg-migrate','DB_PASS':'synthetic-only'}.items():
        monkeypatch.setenv(name,value)
    monkeypatch.setattr(bootstrap,'target',lambda setting,role: URL.create('postgresql+psycopg2',username=role,password='synthetic-only'))
    monkeypatch.setattr(bootstrap,'create_engine',lambda *a,**k:Engine())
    bootstrap.main()
    assert not membership['active'], 'Temporary administrator membership remained after setup'
