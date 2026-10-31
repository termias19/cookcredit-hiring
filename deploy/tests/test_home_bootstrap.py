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
