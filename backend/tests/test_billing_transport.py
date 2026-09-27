from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from services import stripe_service as billing


@pytest.mark.parametrize('environment,key', [('staging', 'sk_live_fixture'), ('production', 'sk_test_fixture')])
def test_deployed_billing_rejects_wrong_mode_before_network(monkeypatch, environment, key):
    monkeypatch.setenv('K_SERVICE', 'hiring')
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', environment)
    monkeypatch.setenv('STRIPE_SECRET_KEY', key)
    client = Mock()
    monkeypatch.setattr(billing.stripe, 'StripeClient', client)
    with pytest.raises(RuntimeError):
        billing.create_billing_customer(email='owner@example.test', name='Test', org_id='org', idempotency_key='stable')
    client.assert_not_called()


def test_hiring_requests_have_bounded_io_metadata_and_stable_checkout_idempotency(monkeypatch):
    monkeypatch.setenv('COOKCREDIT_ENVIRONMENT', 'staging')
    monkeypatch.setenv('STRIPE_SECRET_KEY', 'rk_test_fixture')
    monkeypatch.setattr(billing, 'FRONTEND_URL', 'https://hiring.example.test')
    client = Mock()
    client.customers.create.return_value = SimpleNamespace(id='cus_hiring')
    client.checkout.sessions.create.return_value = SimpleNamespace(id='cs_hiring', url='https://checkout.stripe.test/session')
    client.billing_portal.sessions.create.return_value = SimpleNamespace(url='https://billing.stripe.test/portal')
    transport = Mock(return_value='bounded-http')
    factory = Mock(return_value=client)
    monkeypatch.setattr(billing.stripe, 'RequestsClient', transport)
    monkeypatch.setattr(billing.stripe, 'StripeClient', factory)
    assert billing.create_billing_customer(email='owner@example.test', name='Test', org_id='org', idempotency_key='stable') == 'cus_hiring'
    for _ in range(2):
        billing.create_subscription_checkout(customer_id='cus_hiring', org_id='org', request_id='request', price_id='price_hiring')
    billing.create_billing_portal(customer_id='cus_hiring')
    billing.retrieve_billing_subscription('sub_hiring')
    assert all(call.kwargs == {'timeout': 5} for call in transport.call_args_list)
    assert all(call.kwargs['max_network_retries'] == 0 for call in factory.call_args_list)
    first, second = client.checkout.sessions.create.call_args_list
    assert first == second
    params, options = first.args
    assert params['metadata']['cookcredit_product'] == 'hiring'
    assert params['subscription_data']['metadata']['cookcredit_org_id'] == 'org'
    assert options['idempotency_key'] == 'org:org:team:price_hiring-checkout:request'
    assert 'orderKind' not in params['metadata']
