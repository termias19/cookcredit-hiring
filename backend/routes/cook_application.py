"""Cook application funnel.

An eater applies to become a cook: they fill a bio and take the on-camera
chopping test (in sequence), then submit. We persist the application on their
CookProfile, stamp applied_at (-> status 'pending'), and email the team at
connectwithus@cookcredit.com for MANUAL review. We do NOT grant the 'cook' role
here — that happens only when the team approves (sets cook_profiles.approved),
which is what unlocks the in-app "switch to cooking" choice.

  POST /api/cook-application   { bio, cuisines[], specialties[], pricePerHour, travelRadiusMiles, baseCity? }
"""
import logging
import os
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, g

from extensions import limiter
from middleware.auth import require_auth
from services.database import db_session
from models import CookProfile

log = logging.getLogger(__name__)

cook_application_bp = Blueprint("cook_application", __name__)

APPLICATIONS_EMAIL = os.environ.get("COOK_APPLICATIONS_EMAIL", "connectwithus@cookcredit.com")
MAX_BIO = 2000


def _send_application_email(applicant_name, applicant_email, snap):
    """Best-effort notify the team. No-ops (logs) if SendGrid isn't configured.
    Takes a plain dict snapshot so it can run AFTER the DB commit (no held conn)."""
    sg_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("SENDGRID_FROM_EMAIL", "noreply@cookcredit.com")
    score = f"{snap['skill_score']:.1f}" if snap.get("skill_score") is not None else "not taken"
    tier = snap.get("skill_tier") or "—"
    body = (
        f"<h2>New cook application</h2>"
        f"<p><strong>{applicant_name or 'A user'}</strong> ({applicant_email or 'no email'}) "
        f"applied to become a cook.</p>"
        f"<ul>"
        f"<li><strong>Skill test:</strong> {score} (tier {tier}, "
        f"{'verified' if snap.get('skill_verified') else 'not verified'})</li>"
        f"<li><strong>Cuisines:</strong> {', '.join(snap.get('cuisines') or []) or '—'}</li>"
        f"<li><strong>Specialties:</strong> {', '.join(snap.get('specialties') or []) or '—'}</li>"
        f"<li><strong>Rate:</strong> ${snap.get('price_per_hour') or '—'}/hr · "
        f"radius {snap.get('travel_radius_miles') or '—'} mi</li>"
        f"</ul>"
        f"<p><strong>Bio:</strong><br>{(snap.get('bio') or '').replace(chr(10), '<br>')}</p>"
        f"<p>Review and approve in the admin to grant cook access.</p>"
    )
    if not sg_key:
        log.warning("SENDGRID_API_KEY not set — cook application from %s stored but not emailed to %s",
                    applicant_email, APPLICATIONS_EMAIL)
        return False
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(sg_key)
        msg = Mail(from_email=from_email, to_emails=APPLICATIONS_EMAIL,
                   subject=f"Cook application — {applicant_name or applicant_email or 'new applicant'}",
                   html_content=body)
        sg.send(msg)
        return True
    except Exception:
        log.exception("SendGrid failed for cook application from %s", applicant_email)
        return False


@cook_application_bp.route("", methods=["POST"])
@cook_application_bp.route("/", methods=["POST"])
@require_auth
@limiter.limit("5 per hour", key_func=lambda: g.user_id)
def submit_cook_application():
    data = request.get_json(silent=True) or {}
    bio = (data.get("bio") or "").strip()
    cuisines = data.get("cuisines") or []
    specialties = data.get("specialties") or []
    if not bio:
        return jsonify({"error": "A short bio is required"}), 400
    if len(bio) > MAX_BIO:
        return jsonify({"error": "Bio is too long"}), 413
    if not isinstance(cuisines, list) or not cuisines:
        return jsonify({"error": "Pick at least one cuisine"}), 400

    def _num(v, lo, hi):
        """Parse to float and clamp into [lo, hi] (price_per_hour is Numeric(6,2),
        travel_radius_miles Numeric(4,1) — out-of-range would 500 on flush)."""
        try:
            return max(lo, min(hi, float(v)))
        except (TypeError, ValueError):
            return None

    with db_session() as session:
        cp = session.get(CookProfile, g.user_id)
        if cp is None:
            cp = CookProfile(user_id=g.user_id)
            session.add(cp)
        # Persist the application details. Do NOT touch user.roles — the 'cook'
        # role is granted only on team approval.
        cp.bio = bio
        cp.cuisines = [str(c) for c in cuisines][:20]
        cp.specialties = [str(s) for s in specialties][:20] if isinstance(specialties, list) else []
        rate = _num(data.get("pricePerHour"), 0, 9999.99)
        radius = _num(data.get("travelRadiusMiles"), 0, 999.9)
        if rate is not None:
            cp.price_per_hour = rate
        if radius is not None:
            cp.travel_radius_miles = radius
        if data.get("baseCity"):
            cp.base_city = str(data["baseCity"])[:120]
        # Stamp the application time only if not already an approved cook.
        if not cp.approved:
            cp.applied_at = datetime.now(timezone.utc)
        session.flush()
        status = "approved" if cp.approved else "pending"
        # Snapshot for the email so it can be sent AFTER the commit (no held conn).
        snap = {
            "skill_score": float(cp.skill_score) if cp.skill_score is not None else None,
            "skill_tier": cp.skill_tier, "skill_verified": cp.skill_verified,
            "cuisines": cp.cuisines, "specialties": cp.specialties,
            "price_per_hour": float(cp.price_per_hour) if cp.price_per_hour is not None else None,
            "travel_radius_miles": float(cp.travel_radius_miles) if cp.travel_radius_miles is not None else None,
            "bio": cp.bio,
        }

    # Outside the transaction: the network call no longer holds a pooled connection.
    emailed = _send_application_email(g.name, g.email, snap)
    return jsonify({"ok": True, "applicationStatus": status, "emailed": emailed}), 200
