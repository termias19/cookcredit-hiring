"""Exercise the real Hiring error handler without cloud, SQL or provider calls."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy.exc import OperationalError


@pytest.fixture
def app(monkeypatch):
    import dotenv
    from services import database, runtime_config, scoring_dispatch
    monkeypatch.setattr(dotenv,'load_dotenv',lambda:None)
    monkeypatch.setattr(database,'init_db',lambda:None)
    monkeypatch.setattr(runtime_config,'validate_runtime_configuration',lambda:None)
    monkeypatch.setattr(scoring_dispatch,'validate_dispatch_configuration',lambda:None)
    monkeypatch.setenv('MARKET','ET')
    monkeypatch.setenv('RATELIMIT_STORAGE_URI','memory://')
    monkeypatch.setenv('FRONTEND_URL','https://hiring.example.test')
    spec=importlib.util.spec_from_file_location('isolated_hiring_error_app',Path(__file__).parents[1]/'app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.app.config.update(TESTING=True,RATELIMIT_ENABLED=False)
    return module.app


@pytest.mark.parametrize('endpoint,path,state,retryable', [
    ('auth.dispatch_emails','/api/auth/internal/dispatch-emails','57P01',True),
    ('auth.dispatch_emails','/api/auth/internal/dispatch-emails','42501',False),
    ('business.candidates','/api/business/candidates','57P01',False),
])
def test_real_handler_correlates_safe_causes_without_hiding_other_endpoints(app,monkeypatch,capsys,endpoint,path,state,retryable):
    def fail():
        raise OperationalError('PRIVATE_SQL@example.test',{'password':'PRIVATE_TOKEN'},SimpleNamespace(pgcode=state))
    monkeypatch.setitem(app.view_functions,endpoint,fail)
    capsys.readouterr()
    response=app.test_client().open(path+'?private=PRIVATE_TOKEN',method='POST' if 'dispatch' in endpoint else 'GET',
        headers={'X-Request-ID':'PRIVATE_TOKEN','Authorization':'Bearer PRIVATE_TOKEN'})
    assert response.status_code==503 and response.headers['Retry-After']=='5'
    reference=response.headers['X-Request-ID']
    assert len(reference)==32 and response.json['requestId']==reference
    output=capsys.readouterr().out
    events=[json.loads(line) for line in output.splitlines() if line.startswith('{')]
    dependency=next(e for e in events if e['event']=='dependency_unavailable')
    failed=next(e for e in events if e['event']=='request_failed')
    for event in (dependency,failed):
        assert event['severity']=='ERROR'
        assert event['retryableBackground'] is retryable
        assert event['sqlState']==state and event['requestId']==reference
    assert 'PRIVATE_TOKEN' not in output and 'PRIVATE_SQL' not in output
