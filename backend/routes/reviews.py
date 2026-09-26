"""
Reviews — stub for Task 20 (marketplace reviews).

The old house-meal review system has been removed.
This will be rebuilt as bidirectional booking reviews.
"""

from flask import Blueprint, jsonify

reviews_bp = Blueprint("reviews", __name__)


@reviews_bp.route("/", methods=["GET"])
def reviews_placeholder():
    return jsonify({"message": "Reviews endpoint — not yet implemented"}), 501
