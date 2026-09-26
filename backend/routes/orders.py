"""Orders: the settlement layer for a beam pick.

The beam flow is payment-agnostic; an Order row is created (optionally) when the eater chooses a
cook with a payment method (see routes/beams.py choose). This blueprint drives the ONLINE payment
for that order — Cash-on-delivery needs nothing here (it is settled in person on delivery).

  POST /api/orders/<id>/pay        initialize the online checkout (ET: Chapa) -> { checkoutUrl }
  POST /api/orders/<id>/verify     confirm payment by reference after the eater returns from Chapa

Market split: get_payment_provider() returns the ET (Chapa) or US (Stripe) adapter. Online payment
in the US is not wired (Stripe PaymentIntents) -> 501; cash-on-delivery works in any market.
"""
import logging
import os
import uuid as _uuid

from flask import Blueprint, jsonify, g, request, abort

from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from services.query_helpers import owned_or_404
from services.payments import get_payment_provider
from models import Order, User

orders_bp = Blueprint("orders", __name__)
log = logging.getLogger(__name__)

ONLINE_METHODS = {"chapa", "telebirr", "cbe"}   # all settle through Chapa in ET


def _parse_uuid(s):
    try:
        return _uuid.UUID(str(s))
    except (ValueError, TypeError, AttributeError):
        return None


def _frontend_base():
    raw = os.getenv("FRONTEND_URL", "") or ""
    first = next((o.strip() for o in raw.split(",") if o.strip()), "")
    return first or "http://localhost:5173"


@orders_bp.route("/<order_id>/pay", methods=["POST"])
@require_auth
@limiter.limit("30 per hour", key_func=lambda: g.user_id)
def pay_order(order_id):
    oid = _parse_uuid(order_id)
    if oid is None:
        abort(404)
    with db_session() as session:
        order = owned_or_404(session.get(Order, oid), "eater_id", g.user_id)
        if order.payment_method == "cod":
            return jsonify({"error": "Cash-on-delivery orders need no online payment."}), 400
        if order.payment_status == "paid":
            return jsonify({"order": order.to_dict(), "checkoutUrl": None}), 200
        if order.amount is None:
            return jsonify({"error": "This order has no amount to charge."}), 400

        provider = get_payment_provider()
        eater = session.get(User, g.user_id)
        name = (eater.name if eater else None) or ""
        first, _, last = name.partition(" ")
        tx_ref = f"cc-{order.id.hex}-{_uuid.uuid4().hex[:6]}"
        return_url = f"{_frontend_base()}/beam/{order.beam_id}/responses?order={order.id}"
        try:
            result = provider.create_payment_intent(
                amount=order.amount,
                tx_ref=tx_ref,
                email=(eater.email if eater else None) or g.email,
                first_name=first or None,
                last_name=last or None,
                return_url=return_url,
                title="CookCredit",
                description="CookCredit order",
            )
        except NotImplementedError:
            return jsonify({"error": "Online payment is not available in this market yet."}), 501
        except RuntimeError as e:
            log.warning("Chapa initialize failed for order %s: %s", order.id, e)
            return jsonify({"error": "Payment provider is unavailable right now."}), 503

        order.chapa_tx_ref = result.get("tx_ref")
        order.payment_status = result.get("status", "awaiting_payment")
        return jsonify({"order": order.to_dict(), "checkoutUrl": result.get("checkout_url")}), 200


@orders_bp.route("/<order_id>/verify", methods=["POST"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def verify_order(order_id):
    oid = _parse_uuid(order_id)
    if oid is None:
        abort(404)
    with db_session() as session:
        order = owned_or_404(session.get(Order, oid), "eater_id", g.user_id)
        if order.payment_method == "cod":
            return jsonify({"error": "Cash-on-delivery orders are not verified online."}), 400
        if not order.chapa_tx_ref:
            return jsonify({"error": "No online payment to verify for this order."}), 400

        provider = get_payment_provider()
        try:
            result = provider.verify_payment(order.chapa_tx_ref)
        except NotImplementedError:
            return jsonify({"error": "Online payment is not available in this market yet."}), 501
        except RuntimeError as e:
            log.warning("Chapa verify failed for order %s: %s", order.id, e)
            return jsonify({"error": "Payment provider is unavailable right now."}), 503

        if result.get("paid"):
            order.payment_status = "paid"
        elif result.get("status") == "failed":
            order.payment_status = "failed"
        return jsonify({"order": order.to_dict(), "paid": bool(result.get("paid"))}), 200
