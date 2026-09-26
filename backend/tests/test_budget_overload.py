import importlib.util
from pathlib import Path
from sqlalchemy.exc import OperationalError, TimeoutError
from redis.exceptions import ConnectionError as RedisConnectionError
from services import database, runtime_config, scoring_dispatch
from services.email_capacity import EmailQueueBusy


def test_dependency_failures_and_throttling_are_retryable_and_private(monkeypatch, capsys):
    monkeypatch.setattr(database, 'init_db', lambda: None)
    monkeypatch.setattr(runtime_config, 'validate_runtime_configuration', lambda: None)
    monkeypatch.setattr(scoring_dispatch, 'validate_dispatch_configuration', lambda: None)
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'development')
    import extensions
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    monkeypatch.setattr(extensions, 'limiter', Limiter(get_remote_address, storage_uri='memory://'))
    spec = importlib.util.spec_from_file_location('budget_app', Path(__file__).parents[1] / 'app.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.app.config['RATELIMIT_ENABLED'] = True
    errors = {'database': OperationalError('PRIVATE_SQL', {}, Exception('PRIVATE_TOKEN')),
              'pool': TimeoutError('PRIVATE_DSN'), 'redis': RedisConnectionError('PRIVATE_HOST'),
              'mail': EmailQueueBusy('PRIVATE_RECIPIENT')}
    @module.app.get('/budget-failure/<kind>')
    def failed(kind): raise errors[kind]
    @module.app.get('/budget-limit')
    @module.limiter.limit('1 per minute')
    def limited(): return {'ok': True}
    client = module.app.test_client()
    for kind in errors:
        response = client.get('/budget-failure/' + kind + '?secret=PRIVATE_QUERY')
        assert response.status_code == 503
        assert int(response.headers['Retry-After']) > 0
        assert response.json['requestId'] == response.headers['X-Request-ID']
        assert b'PRIVATE' not in response.data
    assert client.get('/budget-limit').status_code == 200
    denied = client.get('/budget-limit')
    assert denied.status_code == 429 and 1 <= int(denied.headers['Retry-After']) <= 61
    assert 'PRIVATE' not in capsys.readouterr().out
