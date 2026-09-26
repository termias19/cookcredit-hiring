from types import SimpleNamespace
from services.integration_access import integration_access
from services.integration_usage import plan_limit


def test_billing_off_alone_does_not_grant_integrations(monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.delenv('INTEGRATION_EARLY_ACCESS_ENABLED', raising=False)
    assert not integration_access(SimpleNamespace(plan='trial'))['api']


def test_early_access_is_explicit_bounded_and_does_not_change_subscription(monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '1')
    org = SimpleNamespace(plan='trial')
    assert integration_access(org)['api'] and integration_access(org)['widget']
    assert integration_access(org)['earlyAccessMonthlyLimit'] == plan_limit('trial') == 100
    assert org.plan == 'trial'
    assert not integration_access(None)['api']
    monkeypatch.setenv('EARLY_ACCESS_MONTHLY_ASSESSMENT_LIMIT', '999999')
    assert plan_limit('trial') == 1000
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '1')
    assert not integration_access(org)['api']


def test_paid_access_is_preserved(monkeypatch):
    monkeypatch.delenv('INTEGRATION_EARLY_ACCESS_ENABLED', raising=False)
    assert integration_access(SimpleNamespace(plan='team'))['widget']
    assert not integration_access(SimpleNamespace(plan='team'))['api']
    assert integration_access(SimpleNamespace(plan='integration'))['api']


def test_open_role_allowance_preserves_trial_and_paid_plans(monkeypatch):
    from services.integration_access import open_role_limit
    org = SimpleNamespace(plan='trial')
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '1')
    assert open_role_limit(org) == 5
    assert org.plan == 'trial'
    assert open_role_limit(None) == 1
    assert open_role_limit(SimpleNamespace(plan='team')) is None
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '1')
    assert open_role_limit(org) == 1
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '0')
    monkeypatch.setenv('INTEGRATION_EARLY_ACCESS_ENABLED', '0')
    assert open_role_limit(org) == 1
