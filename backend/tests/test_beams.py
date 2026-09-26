"""Unit tests for the beam (broadcast-a-craving) feature. Pure — no DB, no Flask app,
no FCM network. Covers the input/URL guards, the best-effort push wrappers, and the
region-pluggable payment adapter. Full route behavior (fan-out, choose, expiry) is
exercised by the manual end-to-end run documented in the PR (needs Postgres + PostGIS).
"""
import uuid
import types
from unittest.mock import patch, MagicMock

import pytest

from routes.beams import _parse_uuid, _valid_craving_photo
from services import notifications as notif
from services import payments


# ── _parse_uuid: a malformed path id must 404, never 500 ─────────────────────────

def test_parse_uuid_accepts_valid():
    u = uuid.uuid4()
    assert _parse_uuid(str(u)) == u


def test_parse_uuid_rejects_garbage():
    assert _parse_uuid("not-a-uuid") is None
    assert _parse_uuid("") is None
    assert _parse_uuid(None) is None
    assert _parse_uuid("12345") is None


# ── _valid_craving_photo: anti-IDOR on the supplied photo URL ────────────────────

BUCKET = "https://firebasestorage.googleapis.com/v0/b/foodnlit-1123e.firebasestorage.app/o/"


def test_valid_craving_photo_accepts_own_namespace():
    uid = "user_abc"
    url = BUCKET + f"cravings%2F{uid}%2Fcraving_123.jpg?alt=media&token=x"
    assert _valid_craving_photo(url, uid) == url


def test_valid_craving_photo_rejects_other_users_path():
    url = BUCKET + "cravings%2Fsomeone_else%2Fcraving_123.jpg?alt=media&token=x"
    assert _valid_craving_photo(url, "user_abc") is None


def test_valid_craving_photo_rejects_non_firebase_host():
    uid = "user_abc"
    url = f"https://evil.example.com/cravings%2F{uid}%2Fx.jpg"
    assert _valid_craving_photo(url, uid) is None


def test_valid_craving_photo_rejects_profiles_namespace():
    # A real upload URL but from the profile (not cravings) namespace -> rejected.
    uid = "user_abc"
    url = BUCKET + f"profiles%2F{uid}%2Fportfolio_1.jpg?alt=media&token=x"
    assert _valid_craving_photo(url, uid) is None


def test_valid_craving_photo_rejects_non_string():
    assert _valid_craving_photo(None, "u") is None
    assert _valid_craving_photo(123, "u") is None


# ── notifications: best-effort, must never raise ─────────────────────────────────

def test_send_push_noop_on_empty_tokens():
    # No tokens -> returns without touching firebase (which would raise if reached).
    assert notif.send_push([], "title", "body", {"k": "v"}) is None
    assert notif.send_push([None, ""], "title", "body") is None


def test_fcm_tokens_for_short_circuits_on_empty():
    # Empty / falsy ids never touch the session.
    assert notif.fcm_tokens_for(None, []) == []
    assert notif.fcm_tokens_for(None, [None, ""]) == []


def test_fcm_tokens_for_returns_non_null_tokens():
    class _Q:
        def __init__(self, rows): self._rows = rows
        def filter(self, *a, **k): return self
        def all(self): return self._rows

    class _Session:
        def __init__(self, rows): self._rows = rows
        def query(self, *a, **k): return _Q(self._rows)

    s = _Session([("tok1",), ("tok2",)])
    assert notif.fcm_tokens_for(s, ["u1", "u2"]) == ["tok1", "tok2"]


def test_notify_beam_created_noop_without_tokens():
    beam = types.SimpleNamespace(id=uuid.uuid4(), craving_text="doro wat",
                                 scope="citywide", city="Addis Ababa")
    assert notif.notify_beam_created([], beam) is None


def test_notify_beam_chosen_noop_without_tokens():
    beam = types.SimpleNamespace(id=uuid.uuid4())
    assert notif.notify_beam_chosen([], beam) is None


# ── payments: region-pluggable settlement adapter (US Stripe / ET Chapa+cash) ─────

def test_stripe_us_adapter_shape():
    p = payments._StripeUS()
    assert p.market == "US" and p.currency == "USD" and p.cash_on_delivery is False


def test_chapa_et_adapter_shape():
    p = payments._ChapaET()
    assert p.market == "ET" and p.currency == "ETB" and p.cash_on_delivery is True


def _chapa_response(payload, status_code=200):
    m = MagicMock()
    m.status_code = status_code
    m.content = b"{}"
    m.json.return_value = payload
    return m


def test_chapa_et_create_payment_intent_initializes(monkeypatch):
    monkeypatch.setenv("CHAPA_SECRET_KEY", "CHASECK_TEST-abc")
    ok = {"status": "success", "data": {"checkout_url": "https://checkout.chapa.co/x"}}
    with patch("requests.post", return_value=_chapa_response(ok)) as post:
        out = payments._ChapaET().create_payment_intent(amount=640, tx_ref="cc-1", email="a@b.co")
    assert out["provider"] == "chapa"
    assert out["tx_ref"] == "cc-1"
    assert out["checkout_url"] == "https://checkout.chapa.co/x"
    assert out["status"] == "awaiting_payment"
    # ETB major units sent as a string; bearer header carries the secret.
    _, kwargs = post.call_args
    assert kwargs["json"]["amount"] == "640" and kwargs["json"]["currency"] == "ETB"
    assert kwargs["headers"]["Authorization"] == "Bearer CHASECK_TEST-abc"


def test_chapa_et_create_payment_intent_requires_key(monkeypatch):
    monkeypatch.delenv("CHAPA_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        payments._ChapaET().create_payment_intent(amount=100)


def test_chapa_et_create_payment_intent_raises_on_chapa_error(monkeypatch):
    monkeypatch.setenv("CHAPA_SECRET_KEY", "k")
    bad = {"status": "failed", "message": "Invalid API Key"}
    with patch("requests.post", return_value=_chapa_response(bad, status_code=401)):
        with pytest.raises(RuntimeError):
            payments._ChapaET().create_payment_intent(amount=100)


def test_chapa_et_verify_payment(monkeypatch):
    monkeypatch.setenv("CHAPA_SECRET_KEY", "k")
    ok = {"status": "success", "data": {"status": "success"}}
    with patch("requests.get", return_value=_chapa_response(ok)):
        out = payments._ChapaET().verify_payment("cc-1")
    assert out["paid"] is True and out["status"] == "success"


def test_chapa_et_verify_payment_unpaid(monkeypatch):
    monkeypatch.setenv("CHAPA_SECRET_KEY", "k")
    pending = {"status": "success", "data": {"status": "pending"}}
    with patch("requests.get", return_value=_chapa_response(pending)):
        out = payments._ChapaET().verify_payment("cc-1")
    assert out["paid"] is False and out["status"] == "pending"


def test_chapa_et_payout_account_still_pending():
    with pytest.raises(NotImplementedError):
        payments._ChapaET().create_payout_account()


def test_get_payment_provider_defaults_to_us():
    # MARKET is read from the env at import; the default test env has no MARKET -> US.
    assert isinstance(payments.get_payment_provider(), payments._StripeUS)
