"""
Auth routes — user sync and profile retrieval.

Firebase Auth handles authentication (token verification in middleware).
User data lives in PostgreSQL.
"""

import logging
import os
import re
from flask import Blueprint, request, jsonify, g
from flask_limiter.util import get_remote_address
from sqlalchemy.dialects.postgresql import insert
from middleware.auth import require_auth, require_verified_email, is_admin_email
from middleware.app_check import require_app_check
from extensions import limiter
from services.database import db_session
from services.email_hygiene import is_disposable_email
from models import User, EaterProfile, CookProfile

auth_bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)


def _grant_cook_if_approved(user):
    """Authorization source of truth: the 'cook' role is granted ONLY when the
    team has approved the cook application (cook_profiles.approved). Flipping
    that flag is therefore sufficient — this self-heals roles on next load."""
    cp = getattr(user, "cook_profile", None)
    if cp and cp.approved and "cook" not in (user.roles or []):
        user.roles = list(user.roles or []) + ["cook"]


def _coerce_active_role(user, requested):
    """activeRole is a display toggle, not an authorization grant. Never let it
    select 'cook' for a user who doesn't hold the cook role."""
    if requested == "cook" and "cook" not in (user.roles or []):
        return user.active_role or "eater"
    return requested


# Account creation is the bot choke point: limit PER IP (a new bot account gets a fresh uid every
# time, so a per-user limit does nothing here). Requires ProxyFix in app.py so we see the real
# client IP behind Cloud Run. ~one signup per person; 40/hr leaves headroom for shared office NATs.
@auth_bp.route("/sync", methods=["POST"])
@require_auth
@limiter.limit("40 per hour;10 per minute", key_func=get_remote_address)
@require_app_check
def sync_user():
    """
    Called after Firebase login/signup on the frontend.
    Creates or updates the user row in PostgreSQL.

    Body: { name, phone, roles: ["eater","cook"], activeRole, hp? }
    """
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify(error='Invalid profile'), 400
    for key, limit in (('name', 200), ('phone', 40)):
        if key in data and (not isinstance(data[key], str) or len(data[key]) > limit):
            return jsonify(error=f'Invalid {key}'), 400
    if 'createOnly' in data and not isinstance(data['createOnly'], bool):
        return jsonify(error='Invalid account recovery mode'), 400

    # Honeypot: `hp` is a hidden field a real user never fills. If it's populated, it's a bot.
    if (data.get("hp") or "").strip():
        log.warning("signup honeypot tripped uid=%s ip=%s", g.user_id, get_remote_address())
        return jsonify({"error": "Invalid submission"}), 400

    with db_session() as session:
        user = session.get(User, g.user_id)
        created = False
        if user is None:
            # New account: reject known disposable/throwaway email domains so we don't mint a row
            # for a throwaway inbox. (require_verified_email already makes such accounts inert, since
            # they can't receive the verification mail — this just stops the row + a cleaner message.)
            if is_disposable_email(g.email):
                log.warning("blocked disposable-email signup uid=%s domain=%s", g.user_id, g.email.rsplit("@", 1)[-1] if g.email else "")
                return jsonify({"error": "Please sign up with a non-disposable email address.",
                                "code": "disposable_email"}), 400
            # Create new user. The 'cook' role is NEVER granted from client input
            # at signup — everyone starts as an eater and becomes a cook only via
            # the reviewed application (bio + skill test + team approval).
            # Two tabs can both observe a missing row. PostgreSQL arbitrates
            # creation atomically; the losing request loads the committed row.
            # Only the winner creates its dependent profile in this transaction.
            created = session.execute(insert(User).values(
                id=g.user_id,
                email=g.email,
                name=data.get("name", ""),
                phone=data.get("phone"),
                roles=["eater"],
                # Persist employer onboarding intent without granting a business seat.
                active_role='business' if data.get('activeRole') == 'business' else 'eater',
            ).on_conflict_do_nothing().returning(User.id)).scalar_one_or_none() is not None
            if created:
                session.add(EaterProfile(user_id=g.user_id))
            user = session.get(User, g.user_id, populate_existing=True)
            # Either unique index can arbitrate concurrent inserts. Never load
            # or merge another identity's account just because its email matches.
            if user is None:
                return jsonify(error='This email is already associated with another account. Contact support.',
                               code='account_conflict'), 409

        # Automatic recovery after a missing /me response must not overwrite a
        # real signup's name or onboarding choice from another browser tab.
        if not created and not data.get('createOnly'):
            if "name" in data:
                user.name = data["name"]
            if "activeRole" in data:
                user.active_role = _coerce_active_role(user, data["activeRole"])
            if "phone" in data:
                user.phone = data["phone"]
        session.flush()
        return jsonify(user.to_dict()), 201 if created else 200


@auth_bp.route("/me", methods=["GET"])
@require_auth
def get_me():
    """Return the current user's profile."""
    with db_session() as session:
        user = session.get(User, g.user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        # Grant the cook role if the team has approved the application (persists).
        _grant_cook_if_approved(user)

        result = user.to_dict()
        result['emailVerified'] = g.email_verified
        # Platform admin (cook-application reviewer) — from the verified-email allowlist.
        result["isAdmin"] = is_admin_email(g.email)
        from services.hiring_access import enabled, is_owner, employer_access_allowed
        result['isAccessOwner'] = enabled() and is_owner(g.email, g.email_verified)
        gated = enabled() or os.environ.get('COOKCREDIT_ENVIRONMENT') == 'staging'
        result['employerAccessAllowed'] = bool(g.email_verified and (not gated or employer_access_allowed(g.email, g.user_id)))

        # Include sub-profiles if they exist
        if user.eater_profile:
            result["eaterProfile"] = user.eater_profile.to_dict()
        if user.cook_profile:
            result["cookProfile"] = user.cook_profile.to_dict()
            # Don't expose stripe account ID to frontend
            result["stripeConnected"] = bool(user.cook_profile.stripe_account_id)

        return jsonify(result)


@auth_bp.route("/me", methods=["PATCH"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def update_me():
    """Update allowed profile fields."""
    data = request.json or {}
    if not isinstance(data, dict):
        return jsonify(error='Invalid profile'), 400
    for key, limit in (('name', 200), ('phone', 40)):
        if key in data and (not isinstance(data[key], str) or len(data[key]) > limit):
            return jsonify(error=f'Invalid {key}'), 400
    if 'name' in data:
        data['name'] = data['name'].strip()
        if not data['name']:
            return jsonify(error='Name is required'), 400

    allowed_user = {"name", "phone", "activeRole", "photoUrl", "fcmToken"}
    allowed_eater = {"addressStreet", "addressCity", "addressState", "addressZip",
                     "dietaryPreferences"}
    allowed_cook = {"bio", "specialties", "cuisines", "pricePerHour",
                    "travelRadiusMiles", "baseCity", "baseState",
                    "yearsExperience", "dietaryCapabilities"}

    with db_session() as session:
        user = session.get(User, g.user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        updated_fields = []

        # Reflect any approval first, so an approved cook may switch to 'cook'.
        _grant_cook_if_approved(user)
        # activeRole is a toggle, never an authorization grant.
        if "activeRole" in data:
            data["activeRole"] = _coerce_active_role(user, data["activeRole"])

        # Update user fields
        field_map = {"name": "name", "phone": "phone", "activeRole": "active_role",
                     "photoUrl": "photo_url", "fcmToken": "fcm_token"}
        for js_key, db_key in field_map.items():
            if js_key in data:
                setattr(user, db_key, data[js_key])
                updated_fields.append(js_key)

        # Update eater profile fields
        if user.eater_profile:
            ep = user.eater_profile
            ep_map = {"addressStreet": "address_street", "addressCity": "address_city",
                      "addressState": "address_state", "addressZip": "address_zip",
                      "dietaryPreferences": "dietary_preferences"}
            for js_key, db_key in ep_map.items():
                if js_key in data:
                    setattr(ep, db_key, data[js_key])
                    updated_fields.append(js_key)

        # Update cook profile fields
        if user.cook_profile:
            cp = user.cook_profile
            cp_map = {"bio": "bio", "specialties": "specialties", "cuisines": "cuisines",
                      "pricePerHour": "price_per_hour", "travelRadiusMiles": "travel_radius_miles",
                      "baseCity": "base_city", "baseState": "base_state",
                      "yearsExperience": "years_experience",
                      "dietaryCapabilities": "dietary_capabilities"}
            for js_key, db_key in cp_map.items():
                if js_key in data:
                    setattr(cp, db_key, data[js_key])
                    updated_fields.append(js_key)

        if not updated_fields:
            return jsonify({"status": "no_op", "message": "No whitelisted fields provided"}), 200

        log.info("PATCH /auth/me uid=%s fields=%s", g.user_id, updated_fields)
        return jsonify({"status": "updated", "fields": updated_fields})


def _email_unavailable():
    # Firebase-native clients send through the Google SDK; custom providers use
    # the durable outbox. Never send through both paths for a single request.
    if (os.environ.get('AUTH_EMAILS_ENABLED') != '1'
            or os.environ.get('AUTH_EMAIL_PROVIDER', 'firebase') not in ('sendgrid', 'google_smtp')):
        return jsonify(error='Account email is temporarily unavailable. Please try again later.'), 503


@auth_bp.route('/email/verification', methods=['POST'])
@require_auth
@limiter.limit('6 per hour;1 per minute', key_func=lambda: g.user_id)
@require_app_check
def request_verification_email():
    unavailable = _email_unavailable()
    if unavailable:
        return unavailable
    if not g.email:
        return jsonify(error='This account has no email address'), 400
    from services.account_email import enqueue_account_email
    if not g.email_verified:
        with db_session() as session:
            result = enqueue_account_email(session, kind='verify', recipient=g.email, user_id=g.user_id)
        if result and not result['queued']:
            return jsonify(error='Please wait before requesting another verification email.',
                           **result), 429, {'Retry-After': str(result['retryAfterSeconds'])}
        return jsonify(accepted=True, **(result or {})), 202
    return jsonify(accepted=True, alreadyVerified=True), 200


@auth_bp.route('/email/password-reset', methods=['POST'])
@limiter.limit('10 per hour;3 per minute', key_func=get_remote_address)
@require_app_check
def request_password_reset():
    unavailable = _email_unavailable()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True)
    email = data.get('email') if isinstance(data, dict) else None
    if not isinstance(email, str) or len(email) > 320 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        return jsonify(error='Enter a valid email address'), 400
    # No account lookup on the public request path; identical response and work
    # for existing and absent users. The protected worker resolves the account.
    from services.account_email import enqueue_account_email
    with db_session() as session:
        enqueue_account_email(session, kind='reset', recipient=email.strip())
    return jsonify(accepted=True, message='If an account exists, a reset link will be sent.'), 202


@auth_bp.route('/complete-verification', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('20 per hour', key_func=lambda: g.user_id)
def complete_verification():
    if os.environ.get('AUTH_WELCOME_EMAILS_ENABLED') != '1':
        return jsonify(verified=True, welcomeEmail='disabled'), 200
    from services.account_email import enqueue_account_email
    with db_session() as session:
        enqueue_account_email(session, kind='welcome', recipient=g.email, user_id=g.user_id)
    return jsonify(verified=True), 202


@auth_bp.route('/internal/dispatch-emails', methods=['POST'])
@limiter.exempt
def dispatch_emails():
    from services.internal_auth import internal_request_authorized
    if not internal_request_authorized(request):
        return jsonify(error='Forbidden'), 403
    if (os.environ.get('AUTH_EMAIL_PROVIDER', 'firebase') not in ('sendgrid', 'google_smtp')
            and os.environ.get('AUTH_WELCOME_EMAILS_ENABLED') != '1'):
        return jsonify(claimed=0, sent=0, skipped=0, failed=0), 200
    from services.account_email import dispatch_account_emails
    result = dispatch_account_emails()
    from services.customer_mail import expand_due_campaigns
    result['offersQueued'] = expand_due_campaigns()
    from services.operations import report_queue_health
    report_queue_health('email')
    return jsonify(result), 503 if result['failed'] else 200
