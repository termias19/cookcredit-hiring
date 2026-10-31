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


@pytest.mark.parametrize('configuration',[bootstrap.STAGING_TARGET,bootstrap.PRODUCTION_TARGET])
def test_managed_admin_retains_owner_access_until_schema_setup_finishes(monkeypatch,configuration):
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
            if 'FROM pg_roles WHERE rolname' in self.statement:return (False,)*5+(configuration[2],)
            if 'FROM pg_database' in self.statement:return (bootstrap.ROLES[0],configuration[2])
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
    monkeypatch.delenv('HOME_STAGING_BOOTSTRAP',raising=False)
    monkeypatch.delenv('HOME_PRODUCTION_BOOTSTRAP',raising=False)
    for name,value in {configuration[5]:'1','COOKCREDIT_ENVIRONMENT':configuration[3],
        'CLOUD_SQL_CONNECTION':configuration[0],'CLOUD_RUN_JOB':configuration[4],'DB_PASS':'synthetic-only'}.items():
        monkeypatch.setenv(name,value)
    monkeypatch.setattr(bootstrap,'target',lambda setting,role,*unused: URL.create('postgresql+psycopg2',username=role,password='synthetic-only'))
    urls=[]
    def engine(url,**unused):
        urls.append(url);return Engine()
    monkeypatch.setattr(bootstrap,'create_engine',engine)
    bootstrap.main()
    assert not membership['active'], 'Temporary administrator membership remained after setup'
    assert [url.database for url in urls]==['postgres',configuration[1]]
    assert all(dict(url.query)=={'host':'/cloudsql/'+configuration[0]}for url in urls)


@pytest.mark.parametrize('configuration',[bootstrap.STAGING_TARGET,bootstrap.PRODUCTION_TARGET])
@pytest.mark.parametrize('change',[
    {'COOKCREDIT_ENVIRONMENT':'development'}, {'CLOUD_SQL_CONNECTION':'toqto-prod:us-central1:unrelated'},
    {'CLOUD_RUN_JOB':'cc-unrelated-job'}, {'CLOUD_RUN_JOB':None},
    {'CLOUD_SQL_CONNECTION':None}, {'COOKCREDIT_ENVIRONMENT':None},
    {'HOME_STAGING_BOOTSTRAP':'1','HOME_PRODUCTION_BOOTSTRAP':'1'},
])
def test_both_environment_guards_reject_before_reading_secrets_or_connecting(monkeypatch,configuration,change):
    for name in ('HOME_STAGING_BOOTSTRAP','HOME_PRODUCTION_BOOTSTRAP','HOME_DATABASE_URL','HOME_RUNTIME_DATABASE_URL','DB_PASS'):
        monkeypatch.delenv(name,raising=False)
    values={configuration[5]:'1','COOKCREDIT_ENVIRONMENT':configuration[3],
        'CLOUD_SQL_CONNECTION':configuration[0],'CLOUD_RUN_JOB':configuration[4],**change}
    for name,value in values.items():
        if value is None:monkeypatch.delenv(name,raising=False)
        else:monkeypatch.setenv(name,value)
    monkeypatch.setattr(bootstrap,'create_engine',lambda *a,**k:pytest.fail('Unauthorized connection attempted'))
    with pytest.raises(RuntimeError):bootstrap.main()


@pytest.mark.parametrize('configuration',[bootstrap.STAGING_TARGET,bootstrap.PRODUCTION_TARGET])
def test_missing_explicit_flag_or_cross_environment_job_and_socket_are_rejected(monkeypatch,configuration):
    other=bootstrap.PRODUCTION_TARGET if configuration==bootstrap.STAGING_TARGET else bootstrap.STAGING_TARGET
    values={'COOKCREDIT_ENVIRONMENT':configuration[3],'CLOUD_SQL_CONNECTION':configuration[0],
        'CLOUD_RUN_JOB':configuration[4],configuration[5]:'1'}
    for name in ('HOME_STAGING_BOOTSTRAP','HOME_PRODUCTION_BOOTSTRAP'):
        monkeypatch.delenv(name,raising=False)
    for name,value in values.items():monkeypatch.setenv(name,value)
    assert bootstrap.guarded_configuration()==configuration
    monkeypatch.delenv(configuration[5])
    with pytest.raises(RuntimeError):bootstrap.guarded_configuration()
    monkeypatch.setenv(configuration[5],'1')
    for name,bad in (('CLOUD_SQL_CONNECTION',other[0]),('CLOUD_RUN_JOB',other[4])):
        monkeypatch.setenv(name,bad)
        with pytest.raises(RuntimeError):bootstrap.guarded_configuration()
        monkeypatch.setenv(name,values[name])


@pytest.mark.parametrize('configuration',[bootstrap.STAGING_TARGET,bootstrap.PRODUCTION_TARGET])
@pytest.mark.parametrize('role_index,setting',[(0,'HOME_DATABASE_URL'),(1,'HOME_RUNTIME_DATABASE_URL')])
def test_exact_socket_database_and_role_are_required_for_each_environment(monkeypatch,configuration,role_index,setting):
    connection,database=configuration[:2]
    role=bootstrap.ROLES[role_index]
    valid=URL.create('postgresql+psycopg2',username=role,password='synthetic-only',
        database=database,query={'host':'/cloudsql/'+connection})
    monkeypatch.setenv(setting,valid.render_as_string(hide_password=False))
    assert bootstrap.target(setting,role,configuration)==valid
    other=bootstrap.PRODUCTION_TARGET if configuration==bootstrap.STAGING_TARGET else bootstrap.STAGING_TARGET
    for change in ({'database':other[1]},{'query':{'host':'/cloudsql/'+other[0]}},
                   {'username':'postgres'},{'port':5433},{'password':''},
                   {'query':{'host':'/cloudsql/'+connection,'options':'-c role=postgres'}}):
        monkeypatch.setenv(setting,valid.set(**change).render_as_string(hide_password=False))
        with pytest.raises(RuntimeError):bootstrap.target(setting,role,configuration)
    with pytest.raises(RuntimeError):bootstrap.target(setting,'postgres',configuration)
    with pytest.raises(RuntimeError):bootstrap.target(setting,role,('arbitrary',)*6)


def test_production_reuses_only_the_existing_production_admin_job():
    assert bootstrap.PRODUCTION_TARGET==(
        'cookcredit-scoring:us-central1:cookcredit-hiring-db','cookcredit_home_prod',
        'cookcredit-home:production:v1','production','cc-hiring-migrate','HOME_PRODUCTION_BOOTSTRAP')
