from types import SimpleNamespace

from routes.stripe import _sync_subscription
from routes import stripe as stripe_routes
from services.integration_usage import plan_limit
from services.partner_integrations import issue_api_key


def org(plan='trial'):
    return SimpleNamespace(
        plan=plan, stripe_customer_id=None, stripe_subscription_id=None,
        subscription_status=None, subscription_price_id=None,
        subscription_period_end=None, subscription_cancel_at_period_end=False,
        billing_updated_at=None,
    )


def subscription(price, status='active'):
    return {
        'id': 'sub_123', 'customer': 'cus_123', 'status': status,
        'items': {'data': [{'price': {'id': price}}]},
        'current_period_end': 1893456000, 'cancel_at_period_end': False,
    }


def test_signed_subscription_price_maps_to_integration_entitlement(monkeypatch):
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    monkeypatch.setenv('STRIPE_INTEGRATION_PRICE_ID', 'price_integration')
    workspace = org()
    _sync_subscription(workspace, subscription('price_integration'))
    assert workspace.plan == 'integration'
    assert workspace.subscription_price_id == 'price_integration'
    _sync_subscription(workspace, subscription('price_unknown'))
    assert workspace.plan == 'trial'


def test_enterprise_contract_is_not_downgraded_by_stripe(monkeypatch):
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    monkeypatch.setenv('STRIPE_INTEGRATION_PRICE_ID', 'price_integration')
    workspace = org('enterprise')
    _sync_subscription(workspace, subscription('price_unknown', status='canceled'), deleted=True)
    assert workspace.plan == 'enterprise'


def test_test_and_live_keys_are_visibly_separate():
    key, raw = issue_api_key(
        org_id='org', name='Sandbox', scopes=['assessments:read'],
        created_by='admin', environment='test')
    assert raw.startswith('cc_test_')
    assert key.key_prefix.startswith('cc_test_')
    assert key.environment == 'test'


def test_usage_limits_are_configurable(monkeypatch):
    monkeypatch.setenv('INTEGRATION_MONTHLY_ASSESSMENT_LIMIT', '2500')
    monkeypatch.setenv('ENTERPRISE_MONTHLY_ASSESSMENT_LIMIT', '25000')
    assert plan_limit('integration') == 2500
    assert plan_limit('enterprise') == 25000


def test_old_subscription_cannot_replace_a_new_active_subscription(monkeypatch):
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    workspace = org()
    workspace.id = 'org-1'
    workspace.stripe_subscription_id = 'sub_new'
    workspace.stripe_customer_id = 'cus_123'
    current = {**subscription('price_team'), 'id': 'sub_new', 'created': 200,
               'metadata': {'cookcredit_org_id': 'org-1'}}
    calls = []
    def retrieve(reference):
        calls.append(reference)
        return current
    monkeypatch.setattr(stripe_routes, 'retrieve_billing_subscription', retrieve)
    stripe_routes._reconcile_subscription(workspace, 'sub_old')
    assert calls == ['sub_new']
    assert workspace.stripe_subscription_id == 'sub_new' and workspace.plan == 'team'


def test_newer_subscription_can_replace_canceled_but_not_cross_workspace(monkeypatch):
    monkeypatch.setenv('STRIPE_TEAM_PRICE_ID', 'price_team')
    workspace = org()
    workspace.id = 'org-1'
    workspace.stripe_subscription_id = 'sub_old'
    workspace.stripe_customer_id = 'cus_123'
    current = {**subscription('price_team', 'canceled'), 'id': 'sub_old', 'created': 100}
    incoming = {**subscription('price_team'), 'id': 'sub_new', 'created': 200,
                'metadata': {'cookcredit_org_id': 'wrong-org'}}
    monkeypatch.setattr(stripe_routes, 'retrieve_billing_subscription', lambda sid: current if sid == 'sub_old' else incoming)
    stripe_routes._reconcile_subscription(workspace, 'sub_new')
    assert workspace.stripe_subscription_id == 'sub_old'
    incoming['metadata']['cookcredit_org_id'] = 'org-1'
    stripe_routes._reconcile_subscription(workspace, 'sub_new')
    assert workspace.stripe_subscription_id == 'sub_new' and workspace.plan == 'team'
