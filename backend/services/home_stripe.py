"""Home adapter for the existing Stripe SDK/account. No global account changes.

Provider I/O is bounded and always called outside SQL transactions. No raw card
details, private household instructions or material labels enter Stripe metadata.
"""
import os
from urllib.parse import urlsplit
import stripe

PRODUCT = 'home_services'


def mode():
    value = os.getenv('HOME_PAYMENT_MODE', 'off')
    if value not in ('off', 'test', 'live'):
        raise RuntimeError('Invalid Home payment mode')
    return value


def client():
    value = mode()
    key = os.getenv('HOME_STRIPE_SECRET_KEY', '').strip()
    prefix = ('sk_live_', 'rk_live_') if value == 'live' else ('sk_test_', 'rk_test_')
    if value == 'off' or not key.startswith(prefix):
        raise RuntimeError('Home Stripe configuration unavailable')
    from services.stripe_service import bounded_stripe_client
    return bounded_stripe_client(key)


def base_url():
    value = os.getenv('HOME_PUBLIC_URL', '').rstrip('/')
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise RuntimeError('Home public URL must be explicit HTTPS')
    return value


def checkout_allowed():
    return mode() != 'off' and os.getenv('HOME_CHECKOUT_ENABLED') == '1'


def transfer_allowed():
    # Deliberately separate from checkout creation: unpaid live acceptance must
    # never enable transfers merely because a live API key is present.
    return mode() != 'off' and os.getenv('HOME_TRANSFERS_ENABLED') == '1'


class StripeHome:
    @property
    def livemode(self):
        return mode() == 'live'

    def verify(self, raw, signature):
        secret = os.getenv('HOME_STRIPE_WEBHOOK_SECRET', '')
        if not secret:
            raise RuntimeError('Home webhook signing is not configured')
        return stripe.Webhook.construct_event(raw, signature, secret, tolerance=300)

    def checkout(self, operation, payload):
        if not checkout_allowed():
            raise RuntimeError('Home checkout disabled')
        meta = {'cookcredit_product': PRODUCT, 'home_payment_id': payload['paymentId'],
                'home_quote_id': payload['quoteId'], 'home_operation_id': operation,
                'home_checkout_attempt': str(payload['attempt'])}
        return client().checkout.sessions.create({
            'mode': 'payment', 'payment_method_types': ['card'],
            'customer_email': payload['email'], 'client_reference_id': payload['paymentId'],
            'line_items': [{'price_data': {'currency': 'usd', 'unit_amount': payload['amountCents'],
                'product_data': {'name': 'CookCredit Home visit — approved maximum'}}, 'quantity': 1}],
            'metadata': meta, 'payment_intent_data': {'metadata': meta,
                'transfer_group': 'home:' + payload['paymentId']},
            'expires_at': payload['expiresAt'],
            'success_url': base_url() + '/#visit/' + payload['bookingId'],
            'cancel_url': base_url() + '/#visit/' + payload['bookingId'],
            'custom_text': {'submit': {'message': 'This is the approved maximum. Unused materials and tax allowance are refunded after review. Helper funds are released after completion.'}},
        }, options={'idempotency_key': 'home:' + operation})

    def payment(self, checkout_id):
        return client().checkout.sessions.retrieve(checkout_id, {'expand': ['payment_intent.latest_charge.balance_transaction']})

    def expire(self, operation, payload):
        current = self.payment(payload['checkoutId'])
        if current.get('status') == 'open':
            return client().checkout.sessions.expire(payload['checkoutId'], {}, options={'idempotency_key': 'home:' + operation})
        return current

    def refund(self, operation, payload):
        if self.livemode and os.getenv('HOME_LIVE_REFUNDS_ENABLED') != '1':
            raise RuntimeError('Home live refunds disabled')
        return client().refunds.create({'payment_intent': payload['paymentIntentId'], 'amount': payload['amountCents'],
            'metadata': {'cookcredit_product': PRODUCT, 'home_payment_id': payload['paymentId'],
                         'home_operation_id': operation}}, options={'idempotency_key': 'home:' + operation})

    def refund_status(self, refund_id):
        return client().refunds.retrieve(refund_id)

    def account(self, account_id):
        return client().accounts.retrieve(account_id)

    def transfer(self, operation, payload):
        if not transfer_allowed():
            raise RuntimeError('Home transfers disabled')
        return client().transfers.create({'amount': payload['amountCents'], 'currency': 'usd',
            'destination': payload['destination'], 'source_transaction': payload['chargeId'],
            'transfer_group': 'home:' + payload['paymentId'],
            'metadata': {'cookcredit_product': PRODUCT, 'home_payment_id': payload['paymentId'],
                         'home_operation_id': operation}}, options={'idempotency_key': 'home:' + operation})

    def reverse(self, operation, payload):
        if self.livemode and os.getenv('HOME_LIVE_REFUNDS_ENABLED') != '1':
            raise RuntimeError('Home live reversals disabled')
        return client().transfers.reversals.create(payload['transferId'], {'amount': payload['amountCents'],
            'metadata': {'cookcredit_product': PRODUCT, 'home_operation_id': operation}},
            options={'idempotency_key': 'home:' + operation})

    def connect(self, operation, payload):
        if os.getenv('HOME_CONNECT_ENABLED') != '1':
            raise RuntimeError('Home account onboarding disabled')
        return client().accounts.create({'type': 'express', 'country': 'US', 'email': payload['email'],
            'capabilities': {'transfers': {'requested': True}},
            'metadata': {'cookcredit_product': PRODUCT, 'home_helper_id': payload['helperId'],
                         'home_operation_id': operation}}, options={'idempotency_key': 'home:' + operation})

    def onboarding(self, account_id):
        return client().account_links.create({'account': account_id, 'type': 'account_onboarding',
            'return_url': base_url() + '/#payout', 'refresh_url': base_url() + '/#payout'})

    def dashboard(self, account_id):
        return client().accounts.login_links.create(account_id, {})
