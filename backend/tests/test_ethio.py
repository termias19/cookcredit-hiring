"""Unit tests for the Ethio-Cook marketplace helpers. Pure — no DB, no Flask app, no network.
Covers server-side order pricing (the client never sets price), the order-status state machine,
and the payment-status mapping. Full route/DB behavior is exercised by a DB-gated integration run.
"""
import pytest

from routes.ethio import _compute_total, _next_status, _payment_status_for, _parse_uuid, _slugify


# ── _compute_total: order is priced from the kitchen's own available menu ─────────
MENU = {"Doro wot": 320.0, "Beyaynetu": 220.0, "Tibs": 450.0}


def test_compute_total_sums_server_prices():
    total, lines = _compute_total(MENU, [{"name": "Doro wot", "qty": 2}, {"name": "Beyaynetu", "qty": 1}])
    assert total == 860.0
    assert lines == [
        {"name": "Doro wot", "price": 320.0, "qty": 2},
        {"name": "Beyaynetu", "price": 220.0, "qty": 1},
    ]


def test_compute_total_ignores_client_supplied_price():
    # A malicious client sends its own price; the server prices from the menu regardless.
    total, lines = _compute_total(MENU, [{"name": "Tibs", "qty": 1, "price": 1}])
    assert total == 450.0 and lines[0]["price"] == 450.0


def test_compute_total_rejects_unknown_or_unavailable_dish():
    with pytest.raises(ValueError):
        _compute_total(MENU, [{"name": "Kitfo", "qty": 1}])   # not in available menu


def test_compute_total_rejects_bad_quantity():
    for bad in (0, -1, 51, 1.5, "2", None):
        with pytest.raises(ValueError):
            _compute_total(MENU, [{"name": "Doro wot", "qty": bad}])


def test_compute_total_rejects_empty_order():
    with pytest.raises(ValueError):
        _compute_total(MENU, [])


# ── _next_status: new -> preparing -> ready -> delivered -> (done) ────────────────
def test_next_status_advances_through_the_flow():
    assert _next_status("new") == "preparing"
    assert _next_status("preparing") == "ready"
    assert _next_status("ready") == "delivered"


def test_next_status_returns_none_when_complete_or_unknown():
    assert _next_status("delivered") is None
    assert _next_status("cancelled") is None
    assert _next_status("bogus") is None


# ── _payment_status_for: COD is owed-on-delivery; online starts unpaid ────────────
def test_payment_status_mapping():
    assert _payment_status_for("cod") == "cod_pending"
    assert _payment_status_for("telebirr") == "pending"
    assert _payment_status_for("chapa") == "pending"
    assert _payment_status_for("cbe") == "pending"


# ── _slugify: kitchen ids are URL slugs derived from the name ─────────────────────
def test_slugify_basic():
    assert _slugify("Tsehay's Kitchen") == "tsehay-s-kitchen"
    assert _slugify("  Abebe  &  Sons!  ") == "abebe-sons"


def test_slugify_never_empty_and_bounded():
    assert _slugify("") == "kitchen"
    assert _slugify("!!!") == "kitchen"
    assert len(_slugify("x" * 200)) <= 40


# ── _parse_uuid: malformed ids -> None (-> 404, never a 500) ──────────────────────
def test_parse_uuid_guards():
    import uuid
    u = uuid.uuid4()
    assert _parse_uuid(str(u)) == u
    assert _parse_uuid("nope") is None
    assert _parse_uuid(None) is None
