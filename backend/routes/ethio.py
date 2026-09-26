"""Ethio-Cook (Addis) marketplace API — kitchens, menus, and food orders.

Public reads (browse kitchens + menu); authed writes (an eater places/sees orders; a cook manages
their kitchen, menu, and incoming orders). Order totals are computed SERVER-SIDE from the kitchen's
own menu prices — the client never sets the price. Amounts are ETB. Settlement of online methods
(telebirr/Chapa/CBE via Chapa) reuses services/payments.py later; cash-on-delivery needs none.

  GET   /api/ethio/kitchens                 public: open kitchens (?q= search, ?cat= dish filter)
  GET   /api/ethio/kitchens/<id>            public: a kitchen + its menu (404 if unknown)
  POST  /api/ethio/orders                   eater: place an order (server-priced)
  GET   /api/ethio/orders/mine              eater: my orders (newest first)
  GET   /api/ethio/kitchens/mine            cook: my kitchen + menu
  PUT   /api/ethio/kitchens/mine            cook: create/update my kitchen (approved cooks only)
  PATCH /api/ethio/kitchens/mine            cook: open/close for orders
  POST  /api/ethio/kitchens/mine/menu       cook: add a dish
  PATCH /api/ethio/menu/<id>                cook: edit a dish (available / price / name)
  GET   /api/ethio/kitchens/mine/orders     cook: incoming orders for my kitchen
  POST  /api/ethio/orders/<id>/advance      cook: advance an order's status
"""
import logging
import re
import uuid as _uuid

from flask import Blueprint, jsonify, g, request, abort

from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from routes.cooks import _clean_str, _num_or_none
from models import CookProfile, Kitchen, MenuItem, EthioOrder, EthioOrderItem

ethio_bp = Blueprint("ethio", __name__)
log = logging.getLogger(__name__)

PAYMENT_METHODS = {"cod", "telebirr", "chapa", "cbe"}
MODES = {"delivery", "pickup"}
STATUS_FLOW = ["new", "preparing", "ready", "delivered"]


# ── pure helpers (unit-tested without a DB) ──────────────────────────────────────
def _parse_uuid(s):
    try:
        return _uuid.UUID(str(s))
    except (ValueError, TypeError, AttributeError):
        return None


def _payment_status_for(method):
    """COD is owed-on-delivery; online methods start unpaid until settlement confirms."""
    return "cod_pending" if method == "cod" else "pending"


def _slugify(name):
    """URL slug for a kitchen id: lowercase, alnum runs joined by '-', max 40 chars."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40]
    return s or "kitchen"


def _next_status(s):
    """Next step in the order lifecycle, or None if already delivered / unknown."""
    try:
        i = STATUS_FLOW.index(s)
    except ValueError:
        return None
    return STATUS_FLOW[i + 1] if i + 1 < len(STATUS_FLOW) else None


def _compute_total(menu_by_name, items):
    """Price an order from the kitchen's OWN available menu. items: [{name, qty}].
    menu_by_name: {name: price} for AVAILABLE dishes only. Returns (total, line_items).
    Raises ValueError on an empty order, bad quantity, or a dish that isn't on the available menu."""
    if not items:
        raise ValueError("empty order")
    total = 0.0
    lines = []
    for it in items:
        name = (it.get("name") or "").strip()
        qty = it.get("qty")
        if not isinstance(qty, int) or qty < 1 or qty > 50:
            raise ValueError("bad quantity")
        if name not in menu_by_name:
            raise ValueError("dish not available: " + name)
        price = float(menu_by_name[name])
        total += price * qty
        lines.append({"name": name, "price": price, "qty": qty})
    return round(total, 2), lines


# ── public reads ─────────────────────────────────────────────────────────────────
@ethio_bp.route("/kitchens", methods=["GET"])
def list_kitchens():
    q = (request.args.get("q") or "").strip().lower()
    cat = (request.args.get("cat") or "").strip().lower()
    with db_session() as session:
        rows = (session.query(Kitchen)
                .filter(Kitchen.is_open.is_(True))
                .order_by(Kitchen.score.desc())
                .all())
        out = []
        for k in rows:
            d = k.to_dict()
            dishes = [s.lower() for s in d["dishes"]]
            if q and q not in d["name"].lower() and not any(q in s for s in dishes):
                continue
            if cat and cat != "all" and not any(cat in s for s in dishes):
                continue
            out.append(d)
        return jsonify({"kitchens": out}), 200


@ethio_bp.route("/kitchens/<kid>", methods=["GET"])
def get_kitchen(kid):
    with db_session() as session:
        k = session.get(Kitchen, kid)
        if k is None:
            return jsonify({"error": "Kitchen not found"}), 404
        return jsonify({"kitchen": k.to_dict(with_menu=True)}), 200


# ── eater: orders ────────────────────────────────────────────────────────────────
@ethio_bp.route("/orders", methods=["POST"])
@require_auth
@limiter.limit("40 per hour", key_func=lambda: g.user_id)
def place_order():
    data = request.get_json(silent=True) or {}
    kid = (data.get("kitchenId") or "").strip()
    mode = (data.get("mode") or "delivery").strip().lower()
    method = (data.get("paymentMethod") or "").strip().lower()
    address = _clean_str(data.get("address"), 300)
    items = data.get("items")

    if mode not in MODES:
        return jsonify({"error": "Choose delivery or pickup."}), 400
    if method not in PAYMENT_METHODS:
        return jsonify({"error": "Choose a payment method."}), 400
    if mode == "delivery" and not address:
        return jsonify({"error": "A delivery address is required."}), 400
    if not isinstance(items, list):
        return jsonify({"error": "No items in the order."}), 400

    with db_session() as session:
        k = session.get(Kitchen, kid)
        if k is None:
            return jsonify({"error": "Kitchen not found"}), 404
        if not k.is_open:
            return jsonify({"error": "This kitchen is closed right now."}), 409
        menu_by_name = {m.name: float(m.price) for m in k.menu if m.available}
        try:
            total, lines = _compute_total(menu_by_name, items)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        order = EthioOrder(
            eater_id=g.user_id, kitchen_id=k.id, mode=mode,
            payment_method=method, payment_status=_payment_status_for(method),
            status="new", total=total, address=address if mode == "delivery" else None,
        )
        order.items = [EthioOrderItem(name=ln["name"], price=ln["price"], qty=ln["qty"]) for ln in lines]
        session.add(order)
        session.flush()
        return jsonify({"order": order.to_dict()}), 201


@ethio_bp.route("/orders/mine", methods=["GET"])
@require_auth
def my_orders():
    with db_session() as session:
        rows = (session.query(EthioOrder)
                .filter(EthioOrder.eater_id == g.user_id)
                .order_by(EthioOrder.created_at.desc())
                .all())
        return jsonify({"orders": [o.to_dict() for o in rows]}), 200


# ── cook: my kitchen + menu ──────────────────────────────────────────────────────
def _my_kitchen(session):
    """The kitchen owned by the current user, or None."""
    return (session.query(Kitchen).filter(Kitchen.cook_id == g.user_id).first())


@ethio_bp.route("/kitchens/mine", methods=["GET"])
@require_auth
def my_kitchen():
    with db_session() as session:
        k = _my_kitchen(session)
        if k is None:
            return jsonify({"kitchen": None}), 200
        return jsonify({"kitchen": k.to_dict(with_menu=True)}), 200


@ethio_bp.route("/kitchens/mine", methods=["PUT"])
@require_auth
@limiter.limit("20 per hour", key_func=lambda: g.user_id)
def upsert_my_kitchen():
    """Create or update the caller's kitchen storefront.

    Server-enforced authorization: only an APPROVED, skill-verified cook may own
    a kitchen (the same visibility rule as the US cook directory). The
    storefront's tier/score are stamped from the verified CookProfile
    credential — never taken from the client."""
    data = request.get_json(silent=True) or {}
    name = _clean_str(data.get("name"), 80)
    hood = _clean_str(data.get("hood"), 60)
    base_price = _num_or_none(data.get("basePrice"), 0, 999999)
    mode = (data.get("mode") or "").strip().lower()

    with db_session() as session:
        cp = session.query(CookProfile).filter(CookProfile.user_id == g.user_id).first()
        if cp is None or not cp.approved or not cp.skill_verified:
            return jsonify({"error": "Only approved, skill-verified cooks can open a kitchen."}), 403

        k = _my_kitchen(session)
        if k is None:
            if not name:
                return jsonify({"error": "A kitchen needs a name."}), 400
            base = _slugify(name)
            slug, i = base, 2
            while session.get(Kitchen, slug) is not None:
                slug, i = f"{base}-{i}", i + 1
            k = Kitchen(id=slug, cook_id=g.user_id, name=name, initial=name[0].upper())
            session.add(k)

        if name:
            k.name = name
            k.initial = name[0].upper()
        if hood:
            k.hood = hood
        if base_price is not None:
            k.base_price = base_price
        if mode in MODES:
            k.mode = mode
        # Credential mirror — server truth only (check constraint: gold|silver|bronze).
        tier = (cp.skill_tier or "").lower()
        k.tier = tier if tier in {"gold", "silver", "bronze"} else "bronze"
        k.score = int(cp.skill_score or 0)
        session.flush()
        return jsonify({"kitchen": k.to_dict(with_menu=True)}), 200


@ethio_bp.route("/kitchens/mine", methods=["PATCH"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def update_my_kitchen():
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        k = _my_kitchen(session)
        if k is None:
            abort(404)
        if "isOpen" in data:
            k.is_open = bool(data["isOpen"])
        return jsonify({"kitchen": k.to_dict(with_menu=True)}), 200


@ethio_bp.route("/kitchens/mine/menu", methods=["POST"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def add_dish():
    data = request.get_json(silent=True) or {}
    name = _clean_str(data.get("name"), 80)
    price = _num_or_none(data.get("price"), 0, 999999)
    if not name or price is None:
        return jsonify({"error": "A dish needs a name and a price."}), 400
    with db_session() as session:
        k = _my_kitchen(session)
        if k is None:
            abort(404)
        item = MenuItem(kitchen_id=k.id, name=name, price=price, available=True)
        session.add(item)
        session.flush()
        return jsonify({"item": item.to_dict()}), 201


@ethio_bp.route("/menu/<item_id>", methods=["PATCH"])
@require_auth
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def edit_dish(item_id):
    iid = _parse_uuid(item_id)
    if iid is None:
        abort(404)
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        item = session.get(MenuItem, iid)
        if item is None:
            abort(404)
        k = session.get(Kitchen, item.kitchen_id)
        if k is None or k.cook_id != g.user_id:
            abort(403)
        if "available" in data:
            item.available = bool(data["available"])
        if "name" in data:
            nm = _clean_str(data.get("name"), 80)
            if nm:
                item.name = nm
        if "price" in data:
            pr = _num_or_none(data.get("price"), 0, 999999)
            if pr is not None:
                item.price = pr
        return jsonify({"item": item.to_dict()}), 200


@ethio_bp.route("/kitchens/mine/orders", methods=["GET"])
@require_auth
def my_kitchen_orders():
    with db_session() as session:
        k = _my_kitchen(session)
        if k is None:
            return jsonify({"orders": []}), 200
        rows = (session.query(EthioOrder)
                .filter(EthioOrder.kitchen_id == k.id)
                .order_by(EthioOrder.created_at.desc())
                .all())
        return jsonify({"orders": [o.to_dict() for o in rows]}), 200


@ethio_bp.route("/orders/<order_id>/advance", methods=["POST"])
@require_auth
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def advance_order(order_id):
    oid = _parse_uuid(order_id)
    if oid is None:
        abort(404)
    with db_session() as session:
        order = session.get(EthioOrder, oid)
        if order is None:
            abort(404)
        k = session.get(Kitchen, order.kitchen_id)
        if k is None or k.cook_id != g.user_id:
            abort(403)   # only the kitchen's owner advances its orders
        nxt = _next_status(order.status)
        if nxt is None:
            return jsonify({"error": "Order is already complete."}), 409
        order.status = nxt
        return jsonify({"order": order.to_dict()}), 200
