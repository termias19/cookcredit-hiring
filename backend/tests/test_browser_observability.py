import json
from flask import Flask
import pytest
from routes.observability import observability_bp
from extensions import limiter


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('FRONTEND_URL', 'https://hiring.cookcredit.com')
    app = Flask(__name__)
    app.config.update(RATELIMIT_ENABLED=False, TESTING=True)
    app.register_blueprint(observability_bp, url_prefix='/api/observability')
    return app.test_client()


def report(**extra):
    return dict(code='render_error', screen='applicant', reference='a' * 32,
                release='b' * 40, **extra)


def test_browser_error_is_bounded_and_contains_no_identity(client, capsys):
    result = client.post('/api/observability/client-error', json=report(),
                         headers={'Origin': 'https://hiring.cookcredit.com'})
    assert result.status_code == 204
    event = json.loads(capsys.readouterr().out.strip())
    assert event['event'] == 'client_error'
    assert event['clientReference'] == 'a' * 32
    assert event['source'] == 'untrusted_browser'
    assert set(event) == {'severity', 'event', 'service', 'revision', 'commit', 'code',
                          'screen', 'clientRelease', 'clientReference', 'requestId', 'source'}


@pytest.mark.parametrize('changes', [
    {'message': 'private@example.test'}, {'stack': 'PRIVATE_TOKEN'},
    {'url': 'https://example.test/?token=PRIVATE'}, {'reference': 'private@example.test'},
    {'release': 'https://untrusted.example'}, {'code': []}, {'screen': {}},
    {'code': 'PRIVATE_ERROR'}, {'screen': '/apply/private-id'},
])
def test_free_text_and_unexpected_shapes_are_rejected(client, capsys, changes):
    payload = report();payload.update(changes)
    result = client.post('/api/observability/client-error', json=payload,
                         headers={'Origin': 'https://hiring.cookcredit.com'})
    assert result.status_code == 400
    assert not capsys.readouterr().out


def test_untrusted_origin_cannot_report(client, capsys):
    for origin in ['', 'https://other.example', 'null']:
        assert client.post('/api/observability/client-error', json=report(),
                           headers={'Origin': origin}).status_code == 403
    assert not capsys.readouterr().out


def test_browser_reports_use_shared_rate_limits(monkeypatch):
    monkeypatch.setenv('FRONTEND_URL', 'https://hiring.cookcredit.com')
    app = Flask(__name__)
    app.config.update(RATELIMIT_STORAGE_URI='memory://', TESTING=True)
    limiter.init_app(app)
    app.register_blueprint(observability_bp, url_prefix='/api/observability')
    with app.test_client() as client:
        results = [client.post('/api/observability/client-error', json=report(),
                   headers={'Origin': 'https://hiring.cookcredit.com'}).status_code for _ in range(11)]
    assert results[:10] == [204] * 10 and results[-1] == 429
    # The limiter object is shared across test apps; do not leak its memory counters.
    limiter.reset()
