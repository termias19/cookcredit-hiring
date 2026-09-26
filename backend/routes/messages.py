"""
Messages — stub for booking-scoped messaging.

The old request-thread messaging has been removed.
This will be rebuilt as booking-scoped conversations in a later task.
"""

from flask import Blueprint, jsonify

messages_bp = Blueprint("messages", __name__)


@messages_bp.route("/", methods=["GET"])
def messages_placeholder():
    return jsonify({"message": "Messages endpoint — not yet implemented"}), 501
