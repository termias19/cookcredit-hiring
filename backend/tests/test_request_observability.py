import importlib.util
import json
from pathlib import Path
from services import database, runtime_config, scoring_dispatch

def test_error_reference_maps_to_private_safe_log(monkeypatch,capsys):
    monkeypatch.setattr(database,'init_db',lambda:None)
    monkeypatch.setattr(runtime_config,'validate_runtime_configuration',lambda:None)
    monkeypatch.setattr(scoring_dispatch,'validate_dispatch_configuration',lambda:None)
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT','development')
    monkeypatch.setenv('RELEASE_COMMIT','a'*40)
    spec=importlib.util.spec_from_file_location('observable_app',Path(__file__).parents[1]/'app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.app.config['RATELIMIT_ENABLED']=False
    @module.app.route('/synthetic-failure')
    def fail():raise RuntimeError('PRIVATE_CANDIDATE_TOKEN_AND_SQL')
    response=module.app.test_client().get('/synthetic-failure?token=PRIVATE_QUERY')
    assert response.status_code==500
    reference=response.json['requestId']
    assert len(reference)==32 and response.headers['X-Request-ID']==reference
    assert response.headers['X-Release-Commit']=='a'*40
    output=capsys.readouterr().out
    assert 'PRIVATE_CANDIDATE_TOKEN_AND_SQL' not in output and 'PRIVATE_QUERY' not in output
    events=[json.loads(x) for x in output.splitlines() if x.startswith('{')]
    exception=next(x for x in events if x['event']=='unhandled_exception')
    assert exception['requestId']==reference and exception['frames'][-1]['function']=='fail'
