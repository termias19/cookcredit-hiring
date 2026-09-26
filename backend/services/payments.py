"""Region-pluggable payment/settlement provider.

The BEAM feature is PAYMENT-AGNOSTIC and never imports this module. Settlement (charging the eater /
paying the cook) is deferred and differs by MARKET:
  US -> Stripe Connect (see services/stripe_service.py)
  ET -> Chapa + cash-on-delivery (Stripe does not operate in Ethiopia; ETB stays in ETB, NBE forex)

get_payment_provider() returns the right adapter for the deploy. Both expose the same interface so
the FUTURE settlement layer stays market-neutral. Only that layer should call this — importing it
from the beam routes would couple the broadcast flow to payments, which we deliberately avoid.
"""
import os
import uuid

MARKET = os.environ.get("MARKET", "US").upper()
CHAPA_BASE_URL = os.getenv("CHAPA_BASE_URL", "https://api.chapa.co/v1")


class _StripeUS:
    market = "US"
    currency = "USD"
    cash_on_delivery = False

    def create_payout_account(self, *args, **kwargs):
        # Lazy import keeps `stripe` out of an ET process entirely.
        from services import stripe_service
        return stripe_service.create_connect_account(*args, **kwargs)

    def create_payment_intent(self, *args, **kwargs):
        raise NotImplementedError("Booking settlement is not wired yet (US: Stripe PaymentIntents)")


class _ChapaET:
    market = "ET"
    currency = "ETB"
    cash_on_delivery = True   # cash is the default flow in Addis; COD takes no online settlement

    def create_payout_account(self, *args, **kwargs):
        raise NotImplementedError("Chapa payout onboarding pending (ET)")

    def create_payment_intent(self, *, amount, tx_ref=None, email=None, first_name=None,
                              last_name=None, return_url=None, callback_url=None,
                              title=None, description=None):
        """Initialize a Chapa hosted checkout (telebirr / Chapa / CBE Birr all settle through
        Chapa). `amount` is ETB in MAJOR units (NOT cents). Returns
        {provider, tx_ref, checkout_url, status} — the caller redirects the eater to checkout_url.
        Cash-on-delivery never reaches here (the order route short-circuits COD).

        Raises RuntimeError if CHAPA_SECRET_KEY is unset (read lazily so a US deploy that never
        calls this does not need the key) or if Chapa rejects the request."""
        import requests  # lazy import: keep payments.py import-safe on a US/no-Chapa deploy
        secret = os.getenv("CHAPA_SECRET_KEY")
        if not secret:
            raise RuntimeError("CHAPA_SECRET_KEY is not set — cannot initialize a Chapa payment")
        tx_ref = tx_ref or f"cookcredit-{uuid.uuid4().hex}"
        payload = {"amount": str(amount), "currency": "ETB", "tx_ref": tx_ref}
        if email:        payload["email"] = email
        if first_name:   payload["first_name"] = first_name
        if last_name:    payload["last_name"] = last_name
        if return_url:   payload["return_url"] = return_url
        if callback_url: payload["callback_url"] = callback_url
        if title or description:
            # Chapa caps customization.title at 16 chars.
            payload["customization"] = {}
            if title:       payload["customization"]["title"] = title[:16]
            if description: payload["customization"]["description"] = description
        resp = requests.post(
            f"{CHAPA_BASE_URL}/transaction/initialize",
            json=payload,
            headers={"Authorization": f"Bearer {secret}"},
            timeout=20,
        )
        body = resp.json() if resp.content else {}
        if resp.status_code >= 400 or body.get("status") != "success":
            raise RuntimeError(f"Chapa initialize failed: {body.get('message') or resp.status_code}")
        return {
            "provider": "chapa",
            "tx_ref": tx_ref,
            "checkout_url": (body.get("data") or {}).get("checkout_url"),
            "status": "awaiting_payment",
        }

    def verify_payment(self, tx_ref):
        """Verify a Chapa transaction by reference. Returns {paid: bool, status: str, raw: dict}.
        Raises RuntimeError if CHAPA_SECRET_KEY is unset."""
        import requests  # lazy import, same reasoning as above
        secret = os.getenv("CHAPA_SECRET_KEY")
        if not secret:
            raise RuntimeError("CHAPA_SECRET_KEY is not set — cannot verify a Chapa payment")
        resp = requests.get(
            f"{CHAPA_BASE_URL}/transaction/verify/{tx_ref}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=20,
        )
        body = resp.json() if resp.content else {}
        status = ((body.get("data") or {}).get("status") or "").lower()
        return {"paid": status == "success", "status": status or "unknown", "raw": body}


def get_payment_provider():
    """The settlement adapter for this deploy's MARKET. US default."""
    return _ChapaET() if MARKET == "ET" else _StripeUS()
