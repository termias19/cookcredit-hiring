"""Hiring approval must not publish a candidate outside their company shares."""
import pytest
from flask import Flask
from middleware import auth
from routes import cooks


@pytest.mark.parametrize('setting', [None, '0', 'true', 'unexpected'])
def test_directory_fails_closed_before_any_profile_lookup(monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv('PUBLIC_COOK_DIRECTORY_ENABLED', raising=False)
    else:
        monkeypatch.setenv('PUBLIC_COOK_DIRECTORY_ENABLED', setting)
    monkeypatch.setattr(auth, '_verify_token', lambda _: {'uid': 'cook', 'email_verified': True})
    monkeypatch.setattr(cooks, 'db_session', lambda: pytest.fail('private profile must not be queried'))
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    app.register_blueprint(cooks.cooks_bp, url_prefix='/cooks')
    client = app.test_client()
    for path in ['/cooks', '/cooks/', '/cooks/private-id']:
        response = client.get(path)
        assert response.status_code == 404
        assert response.json == {'error': 'not found'}
    response = client.post('/cooks/nearby', json={}, headers={'Authorization': 'Bearer test'})
    assert response.status_code == 404
    # The applicant's existing private self-service route still requires identity.
    assert client.get('/cooks/me').status_code == 401
