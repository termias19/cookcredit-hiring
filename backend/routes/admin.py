"""Admin routes — the cook-application review queue.

Replaces the CLI-only approval (dev_db.py approve) with a real, authorized in-app
flow. Admin = an email in the ADMIN_EMAILS allowlist (verified Firebase token, never
client input). Approving flips cook_profiles.approved; the 'cook' role then self-heals
on the applicant's next /api/auth/me.

  GET  /api/admin/cook-applications?status=pending|approved|rejected|all
  POST /api/admin/cook-applications/<uid>/approve
  POST /api/admin/cook-applications/<uid>/reject   body: {note?}
"""
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g

from extensions import limiter
from middleware.auth import require_auth, admin_only
from services.database import db_session
from models import User, CookProfile

admin_bp = Blueprint("admin", __name__)
log = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


@admin_bp.route("/cook-applications", methods=["GET"])
@require_auth
@admin_only
def list_cook_applications():
    """List cook applications for review. Default: pending (applied, not yet approved
    or rejected). status=approved|rejected|all to filter otherwise."""
    status = (request.args.get("status") or "pending").lower()
    with db_session() as session:
        q = (session.query(CookProfile, User)
             .join(User, User.id == CookProfile.user_id)
             .filter(CookProfile.applied_at.isnot(None)))
        if status == "pending":
            q = q.filter(CookProfile.approved.is_(False), CookProfile.rejected_at.is_(None))
        elif status == "approved":
            q = q.filter(CookProfile.approved.is_(True))
        elif status == "rejected":
            q = q.filter(CookProfile.rejected_at.isnot(None))
        # status == "all": no extra filter (any applicant)
        q = q.order_by(CookProfile.applied_at.desc())

        apps = []
        for cp, user in q.all():
            d = cp.to_dict()
            d.update(userId=user.id, name=user.name, email=user.email)
            apps.append(d)
        return jsonify({"applications": apps, "status": status, "count": len(apps)}), 200


@admin_bp.route("/cook-applications/<uid>/approve", methods=["POST"])
@require_auth
@admin_only
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def approve_cook(uid):
    """Approve: the 'cook' role is granted on the applicant's next /api/auth/me."""
    with db_session() as session:
        cp = session.get(CookProfile, uid)
        if cp is None or cp.applied_at is None:
            return jsonify({"error": "no application for this user"}), 404
        cp.approved = True
        cp.rejected_at = None
        log.info("admin %s approved cook %s", g.email, uid)
        return jsonify({"status": "approved", "userId": uid}), 200


@admin_bp.route("/cook-applications/<uid>/reject", methods=["POST"])
@require_auth
@admin_only
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def reject_cook(uid):
    """Reject: record the rejection + optional note, and revoke any cook role."""
    note = (request.get_json(silent=True) or {}).get("note")
    with db_session() as session:
        cp = session.get(CookProfile, uid)
        if cp is None or cp.applied_at is None:
            return jsonify({"error": "no application for this user"}), 404
        cp.approved = False
        cp.rejected_at = _utcnow()
        cp.review_note = (str(note)[:1000] or None) if note else None
        user = session.get(User, uid)
        if user and "cook" in (user.roles or []):
            user.roles = [r for r in user.roles if r != "cook"]
            if user.active_role == "cook":
                user.active_role = "eater"
        log.info("admin %s rejected cook %s", g.email, uid)
        return jsonify({"status": "rejected", "userId": uid}), 200
