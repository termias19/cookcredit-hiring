from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pytest
from services import partner_integrations as partner
from services import partner_rate_limits as budgets


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=True)
    limiter = Limiter(get_remote_address, app=app, storage_uri='memory://', default_limits=['1 per hour'])
    monkeypatch.setattr(partner, 'limiter', limiter)
    monkeypatch.setattr(budgets, 'limiter', limiter)
    monkeypatch.setitem(budgets.BUDGETS, 'company', '3 per hour')
    monkeypatch.setitem(budgets.BUDGETS, 'invalid-ip', '2 per hour')
    monkeypatch.setitem(budgets.BUDGETS, 'lookup-ip', '100 per hour')
    keys = {}
    for token, oid in [('cc_test_a', 'org-a'), ('cc_test_a2', 'org-a'), ('cc_test_b', 'org-b')]:
        keys[partner._api_key_hash(token)] = SimpleNamespace(id=token, org_id=oid, revoked_at=None,
            expires_at=None, scopes=['assessments:read'], environment='test', last_used_at=datetime.now(timezone.utc))
    class Query:
        def filter_by(self, **kwargs): self.key = kwargs['secret_hash']; return self
        def one_or_none(self): return keys.get(self.key)
    @contextmanager
    def session():
        yield SimpleNamespace(query=lambda _: Query(), get=lambda _, oid: SimpleNamespace(plan='integration'))
    monkeypatch.setattr(partner, 'db_session', session)
    for index in range(2):
        def endpoint(): return {'ok': True}
        endpoint.__name__ = 'endpoint_'+str(index)
        app.add_url_rule('/read'+str(index), view_func=partner.require_partner_scope('assessments:read')(endpoint))
    return app.test_client()


def get(client, token, path='/read0'):
    return client.get(path, headers={'Authorization': 'Bearer '+token})


def test_shared_ip_does_not_merge_company_budgets_and_new_keys_do_not_reset_them(client):
    assert [get(client, 'cc_test_a').status_code for _ in range(3)] == [200]*3
    exceeded = get(client, 'cc_test_a2', '/read1')
    assert exceeded.status_code == 429 and int(exceeded.headers['Retry-After']) > 0
    assert [get(client, 'cc_test_b').status_code for _ in range(3)] == [200]*3
    assert get(client, 'cc_test_b').status_code == 429


def test_invalid_credentials_share_an_ip_budget_without_consuming_company_allowance(client):
    assert get(client, 'cc_test_bad1').status_code == 401
    assert get(client, 'cc_test_bad2').status_code == 401
    assert get(client, 'missing').status_code == 429
    assert get(client, 'cc_test_a').status_code == 200


def test_shared_counter_failure_returns_retryable_failure_not_unlimited_access(client, monkeypatch):
    def offline(*args, **kwargs): raise ConnectionError('private provider details')
    monkeypatch.setattr(budgets.limiter.limiter, 'hit', offline)
    result = get(client, 'cc_test_a')
    assert result.status_code == 503 and result.headers['Retry-After'] == '5'
    assert b'private provider' not in result.data


def test_explicitly_disabled_limiter_in_disposable_capacity_harness_is_respected(client, monkeypatch):
    monkeypatch.setattr(budgets.limiter, 'enabled', False)
    assert [get(client, 'cc_test_a').status_code for _ in range(5)] == [200]*5
