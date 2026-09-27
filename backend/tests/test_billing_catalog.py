import pytest
from services.billing_catalog import DEFAULTS, validate_price
from services.integration_access import team_access, open_role_limit
from types import SimpleNamespace

@pytest.mark.parametrize('price', DEFAULTS)
def test_recommended_prices_are_valid(price):
    assert validate_price(price)['amount'] == price['amount']

@pytest.mark.parametrize('change', [dict(amount=True), dict(amount=0), dict(amount=10.5), dict(currency='eur'), dict(plan='enterprise'), dict(interval='week'), dict(limits={'seats': 2}), dict(previousId='bad')])
def test_invalid_price_cannot_be_saved(change):
    with pytest.raises(ValueError): validate_price(DEFAULTS[0] | change)

def test_paid_limits_and_included_access_survive_global_switch(monkeypatch):
    monkeypatch.setenv('BUSINESS_BILLING_ENABLED', '1')
    included = SimpleNamespace(plan='trial', included_access=True)
    assert team_access(included)['seatLimit'] == 5
    assert open_role_limit(included) == 5
    paid = SimpleNamespace(plan='integration', subscription_limits={'seats': 15, 'openRoles': 25})
    assert team_access(paid)['seatLimit'] == 15
    assert open_role_limit(paid) == 25


def test_provider_price_uses_stable_idempotency_and_exact_amount(monkeypatch):
    from services import stripe_service
    calls = []
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_fixture')
    def create(params, options):
        calls.append((params, options))
        return SimpleNamespace(id='price_fixture', livemode=False)
    monkeypatch.setattr(stripe_service.stripe, 'StripeClient', lambda *args, **kwargs:
        SimpleNamespace(products=SimpleNamespace(retrieve=lambda _: None), prices=SimpleNamespace(create=create)))
    values = DEFAULTS[1] | {'id': 'version-fixture'}
    assert stripe_service.create_hiring_price(values) == 'price_fixture'
    assert calls[0][0]['unit_amount'] == 99000
    assert calls[0][0]['recurring'] == {'interval': 'year'}
    assert calls[0][1]['idempotency_key'] == 'hiring-price:version-fixture'


def test_production_cannot_publish_test_prices(monkeypatch):
    from services import stripe_service
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'production')
    monkeypatch.setenv('K_SERVICE', 'cookcredit-hiring')
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'sk_test_fixture')
    monkeypatch.setattr(stripe_service.stripe, 'StripeClient', lambda *a, **k: pytest.fail('No provider operation allowed'))
    with pytest.raises(RuntimeError, match='live key'):
        stripe_service.create_hiring_price(DEFAULTS[0] | {'id': 'fixture'})
