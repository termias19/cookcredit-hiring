"""Ethio-Cook integration tests against a REAL Postgres.

Skipped unless DATABASE_URL points at a Postgres (with the migrations applied, incl. 010). Exercises
the actual data-layer flow the routes drive — a seeded kitchen + menu, an eater placing a
server-priced order, and the cook advancing it through the status lifecycle — using the same models
and helpers as routes/ethio.py.

Run locally:
  docker run -d --name cc-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=cookcredit -p 5544:5432 postgis/postgis:16-3.4
  cd backend && DATABASE_URL=postgresql://postgres:postgres@localhost:5544/cookcredit python migrations/run_migrations.py
  DATABASE_URL=postgresql://postgres:postgres@localhost:5544/cookcredit pytest tests/test_ethio_integration.py -v
"""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="needs a Postgres (set DATABASE_URL) for the ethio integration tests",
)

from services.database import db_session, init_db  # noqa: E402
from models import User, CookProfile, Kitchen, MenuItem, EthioOrder, EthioOrderItem  # noqa: E402
from routes.ethio import _compute_total, _payment_status_for, _next_status, _slugify  # noqa: E402


def test_ethio_order_flow_end_to_end():
    init_db()
    sfx = uuid.uuid4().hex[:8]
    eater_id, cook_id, kid = f"it_eat_{sfx}", f"it_cook_{sfx}", f"it_kitchen_{sfx}"

    try:
        # ── arrange: an eater, a cook, and the cook's kitchen + menu
        with db_session() as s:
            s.add(User(id=eater_id, email=f"{eater_id}@t.com", name="Eater", roles=["eater"], active_role="eater"))
            s.add(User(id=cook_id, email=f"{cook_id}@t.com", name="Cook", roles=["eater", "cook"], active_role="cook"))
            s.flush()
            s.add(Kitchen(id=kid, cook_id=cook_id, name="IT Kitchen", initial="I", tier="gold",
                          score=90, rating=4.8, hood="Bole", base_price=320, mode="delivery", is_open=True))
            s.flush()
            s.add(MenuItem(kitchen_id=kid, name="Doro wot", price=320, available=True))
            s.add(MenuItem(kitchen_id=kid, name="Beyaynetu", price=220, available=True))
            s.add(MenuItem(kitchen_id=kid, name="Kitfo", price=400, available=False))   # sold out

        # ── act 1: eater places a server-priced order (mirrors routes.ethio.place_order)
        with db_session() as s:
            k = s.get(Kitchen, kid)
            menu_by_name = {m.name: float(m.price) for m in k.menu if m.available}
            # a sold-out dish must not be orderable
            with pytest.raises(ValueError):
                _compute_total(menu_by_name, [{"name": "Kitfo", "qty": 1}])
            total, lines = _compute_total(menu_by_name, [{"name": "Doro wot", "qty": 2}, {"name": "Beyaynetu", "qty": 1}])
            assert total == 860.0
            order = EthioOrder(eater_id=eater_id, kitchen_id=kid, mode="delivery",
                               payment_method="cod", payment_status=_payment_status_for("cod"),
                               status="new", total=total, address="Bole, Addis Ababa")
            order.items = [EthioOrderItem(name=ln["name"], price=ln["price"], qty=ln["qty"]) for ln in lines]
            s.add(order); s.flush()
            order_id = order.id
            assert order.payment_status == "cod_pending"

        # ── assert: the order persisted with its line items and is on both sides
        with db_session() as s:
            o = s.get(EthioOrder, order_id)
            assert o is not None and float(o.total) == 860.0 and o.status == "new"
            assert {it.name: it.qty for it in o.items} == {"Doro wot": 2, "Beyaynetu": 1}
            assert o.eater_id == eater_id and o.kitchen_id == kid
            mine = s.query(EthioOrder).filter(EthioOrder.eater_id == eater_id).all()
            inbox = s.query(EthioOrder).filter(EthioOrder.kitchen_id == kid).all()
            assert len(mine) == 1 and len(inbox) == 1

        # ── act 2: cook advances the order new -> preparing -> ready -> delivered
        with db_session() as s:
            o = s.get(EthioOrder, order_id)
            for expected in ("preparing", "ready", "delivered"):
                o.status = _next_status(o.status)
                assert o.status == expected
            assert _next_status(o.status) is None   # delivered is terminal

        with db_session() as s:
            assert s.get(EthioOrder, order_id).status == "delivered"

    finally:
        # ── cleanup (order/items cascade from the order; kitchen/menu cascade from the kitchen)
        with db_session() as s:
            o = s.query(EthioOrder).filter(EthioOrder.eater_id == eater_id).first()
            if o:
                s.delete(o)
        with db_session() as s:
            k = s.get(Kitchen, kid)
            if k:
                s.delete(k)
            for uid in (eater_id, cook_id):
                u = s.get(User, uid)
                if u:
                    s.delete(u)


def test_kitchen_create_mirrors_verified_credential():
    """PUT /kitchens/mine data-layer flow: slug uniqueness + the tier/score stamp
    coming from the approved CookProfile, never from client input."""
    init_db()
    sfx = uuid.uuid4().hex[:8]
    cook_id = f"it_kcook_{sfx}"
    made_slugs = []

    try:
        with db_session() as s:
            s.add(User(id=cook_id, email=f"{cook_id}@t.com", name="Cook", roles=["eater", "cook"], active_role="cook"))
            s.flush()
            s.add(CookProfile(user_id=cook_id, bio="it", approved=True, skill_verified=True,
                              skill_tier="gold", skill_score=91.5))

        # create with a slug collision: same name twice -> second gets -2
        for expected_suffix in ("", "-2"):
            with db_session() as s:
                cp = s.query(CookProfile).filter(CookProfile.user_id == cook_id).first()
                assert cp.approved and cp.skill_verified
                base = _slugify("Selam Kitchen IT " + sfx)
                slug, i = base, 2
                while s.get(Kitchen, slug) is not None:
                    slug, i = f"{base}-{i}", i + 1
                assert slug == base + expected_suffix
                k = Kitchen(id=slug, cook_id=None if expected_suffix else cook_id,
                            name="Selam Kitchen IT " + sfx, initial="S",
                            tier=(cp.skill_tier or "bronze"), score=int(cp.skill_score or 0))
                s.add(k)
                s.flush()
                made_slugs.append(slug)
                assert k.tier == "gold" and k.score == 91

    finally:
        with db_session() as s:
            for slug in made_slugs:
                k = s.get(Kitchen, slug)
                if k:
                    s.delete(k)
            cp = s.query(CookProfile).filter(CookProfile.user_id == cook_id).first()
            if cp:
                s.delete(cp)
            u = s.get(User, cook_id)
            if u:
                s.delete(u)
