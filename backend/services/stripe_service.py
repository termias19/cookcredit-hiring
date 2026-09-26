import stripe
import os
from urllib.parse import urlsplit

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
APP_FEE_PERCENT = float(os.getenv("COOKCREDIT_APP_FEE_PERCENT", 0.10))
FRONTEND_URL    = os.getenv("FRONTEND_URL", "http://localhost:5173")


def _frontend_origin() -> str:
    raw = FRONTEND_URL.split(',', 1)[0].strip().rstrip('/')
    parsed = urlsplit(raw)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise RuntimeError('FRONTEND_URL must be an absolute URL for Stripe redirects')
    return f'{parsed.scheme}://{parsed.netloc}'


# ─── Connect Account (Cook Onboarding) ────────────────────────────────────────

def create_connect_account(email: str, name: str) -> dict:
    parts   = name.strip().split()
    account = stripe.Account.create(
        type="express",
        country="US",
        email=email,
        capabilities={
            "card_payments": {"requested": True},
            "transfers":     {"requested": True},
        },
        business_type="individual",
        business_profile={
            "mcc":                 "5812",
            "product_description": "Home-cooked meal tips via CookCredit",
            "url":                 "https://cookcredit.com",
        },
        individual={
            "first_name": parts[0],
            "last_name":  parts[-1] if len(parts) > 1 else parts[0],
            "email":      email,
        },
        settings={
            "payouts": {
                "schedule": {"interval": "daily", "delay_days": 2}
            }
        },
    )
    return {"stripe_account_id": account.id, "status": account.charges_enabled}


def create_onboarding_link(stripe_account_id: str, cook_id: str) -> str:
    link = stripe.AccountLink.create(
        account=stripe_account_id,
        refresh_url=f"{FRONTEND_URL}/#/profile",
        return_url=f"{FRONTEND_URL}/#/profile",
        type="account_onboarding",
    )
    return link.url


def create_login_link(stripe_account_id: str) -> str:
    link = stripe.Account.create_login_link(stripe_account_id)
    return link.url


def get_account_status(stripe_account_id: str) -> dict:
    account = stripe.Account.retrieve(stripe_account_id)
    return {
        "charges_enabled":   account.charges_enabled,
        "payouts_enabled":   account.payouts_enabled,
        "details_submitted": account.details_submitted,
        "requirements":      account.requirements.currently_due,
    }


def get_cook_balance(stripe_account_id: str) -> dict:
    balance   = stripe.Balance.retrieve(stripe_account=stripe_account_id)
    available = sum(b["amount"] for b in balance.available) / 100
    pending   = sum(b["amount"] for b in balance.pending)   / 100
    return {"available": available, "pending": pending, "currency": "usd"}


# ─── Webhooks ─────────────────────────────────────────────────────────────────

def construct_webhook_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(
        payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET")
    )


# ─── Business subscriptions ──────────────────────────────────────────────────

def retrieve_billing_subscription(subscription_id: str):
    # Bounded I/O while holding the workspace billing lock. Stripe retries the
    # event when retrieval fails; never apply an old event snapshot as fallback.
    client = stripe.StripeClient(os.environ.get('STRIPE_SECRET_KEY', ''),
        http_client=stripe.RequestsClient(timeout=5), max_network_retries=0)
    return client.subscriptions.retrieve(subscription_id)

def create_billing_customer(*, email: str, name: str, org_id: str, idempotency_key: str) -> str:
    customer = stripe.Customer.create(
        email=email, name=name,
        metadata={'cookcredit_org_id': org_id},
        idempotency_key=idempotency_key,
    )
    return customer.id


def create_subscription_checkout(*, customer_id: str, org_id: str, request_id: str,
                                 plan: str = 'team') -> dict:
    if plan not in ('team', 'integration'):
        raise ValueError('Unsupported subscription plan')
    price_id = os.getenv('STRIPE_INTEGRATION_PRICE_ID' if plan == 'integration'
                         else 'STRIPE_TEAM_PRICE_ID', '').strip()
    if not price_id:
        raise RuntimeError(f'{plan.title()} billing is not configured')
    origin = _frontend_origin()
    checkout = stripe.checkout.Session.create(
        mode='subscription', customer=customer_id,
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=f'{origin}/business/billing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{origin}/business/billing?checkout=cancelled',
        client_reference_id=org_id,
        metadata={'cookcredit_org_id': org_id, 'plan': plan},
        subscription_data={'metadata': {'cookcredit_org_id': org_id, 'plan': plan}},
        allow_promotion_codes=True,
        idempotency_key=f'org:{org_id}:{plan}-checkout:{request_id}',
    )
    return {'id': checkout.id, 'url': checkout.url}


def create_billing_portal(*, customer_id: str) -> str:
    portal = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f'{_frontend_origin()}/business/billing',
    )
    return portal.url


# ─── Booking Payments (authorize & capture) ──────────────────────────────────
# Will be implemented in Tasks 17-19. The pattern is:
#   1. authorize_booking()  → PaymentIntent with capture_method='manual'
#   2. capture_booking()    → PaymentIntent.capture(actual_amount)
#   3. cancel_booking_payment() → PaymentIntent.cancel()
