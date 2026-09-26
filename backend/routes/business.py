"""
B2B workspace API — org activation, role postings (scorecards), candidate pipeline, shortlists,
and the verified-candidate roster.

  POST /api/business/activate            -> grant business role + create/get org
  GET  /api/business/org
  GET  /api/business/roles               POST /api/business/roles
  GET  /api/business/role/<id>           (role + pipeline)
  POST /api/business/role/<id>/stage     { cookId, stage }
  POST /api/business/role/<id>/star      { cookId }
  POST /api/business/role/<id>/notice    { cookId, ... }   (LL144 candidate notice)
  GET  /api/business/shortlist           POST /api/business/shortlist { cookId }
  GET  /api/business/candidates          (verified-cook roster)
  GET  /api/business/candidate/<id>/video                  (biometric — tightest gate)

AUTHORIZATION MODEL (the security contract — keep these invariants when adding routes):
  1. Every route is behind @require_auth, which sets g.user_id/g.email from a VERIFIED Firebase
     token. Identity is never taken from the request body.
  2. Org-scoping (anti-IDOR): role-scoped reads/writes resolve the role through _role_owned(), which
     returns it ONLY if it belongs to the caller's org. Shortlist/roster derive from _org_for(caller).
     A caller can never reach another org's data by guessing a UUID.
  3. Role gate: reads that expose the cook pool (roster, biometric video) AND every pipeline/shortlist
     WRITE require the 'business' role via _require_business() — not bare org membership. Membership
     and the role are granted together today, but the role is the authorization anchor so a future
     teammate/viewer-seat flow can't silently widen access.
  4. cookId hygiene: any route that writes a client-supplied cookId validates it first —
     _verified_cook() for the shortlist (a verified-cook pool by definition) and _cook_exists() for
     the pipeline (allows pre-verification invited/assessing cooks, rejects non-cook/arbitrary ids).
     Unvalidated ids would otherwise seed AedtAuditLog rows via role_detail() (the audit-of-record).
  5. Biometric video (candidate_video) is gated tightest: business role AND the cook must be in one
     of THIS org's pipelines (_cook_in_org_pipeline) AND skill_verified. Never serialized in to_dict.
  6. Rate limits: mutating/expensive routes carry a per-user @limiter.limit. NOTE the limiter uses
     memory:// (per-process) unless RATELIMIT_STORAGE_URI/REDIS_URL is set — configure Redis before
     running >1 instance (see deploy/config.sh).
"""
import logging
import hashlib
import html
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request, g, make_response

from services.landmark_recording import landmarks_url
from extensions import limiter
from middleware.auth import require_auth, require_verified_email
from services.database import db_session
from services.matching import match_role, FEATURE_WEIGHTS
from services.assessment_media import playback_url, PLAYBACK_TTL_SECONDS
from services.assessment_outcomes import evaluate_assessment
from services.live_motion_evidence import hiring_motion_criteria
from services.integration_access import open_role_limit
from services.hiring_presentation import assessment_instructions
from services import company_branding, hiring_reviews
from models import HiringApplication, HiringApplicationEvent, AssessmentShare, AssessmentAccessLog, SkillAttempt, ATTEMPT_TERMINAL
from models import (User, CookProfile, Org, OrgMembership, OrgInvitation, RolePosting,
                    PipelineCard, Shortlist, ShortlistMember, ResumeKeypoints,
                    AedtAuditLog, CandidateNotice, OptOutRequest)

log = logging.getLogger(__name__)
business_bp = Blueprint("business", __name__)

STAGES = ["invited", "assessing", "verified", "shortlisted", "contacted", "hired", "not_selected"]
SEAT_PERMISSIONS = {
    "admin": {"workspace", "roles", "candidates", "evidence", "decisions", "billing"},
    "recruiter": {"workspace", "roles", "candidates", "evidence", "decisions"},
    "hiring_manager": {"workspace", "roles", "candidates", "evidence", "decisions"},
    "viewer": {"workspace"},
}
SEAT_ROLES = set(SEAT_PERMISSIONS)


def _utcnow():
    return datetime.now(timezone.utc)


def _send_workspace_invite(*, recipient, org_name, seat_role, invite_url):
    """Best-effort delivery. The invitation is persisted even when email is unavailable."""
    key = os.environ.get('SENDGRID_API_KEY', '').strip()
    if not key:
        return False
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        safe_org, safe_url = html.escape(org_name), html.escape(invite_url, quote=True)
        message = Mail(
            from_email=os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@cookcredit.com'),
            to_emails=recipient,
            subject=f'Join {org_name} on CookCredit',
            html_content=(f'<p>{safe_org} invited you to a {html.escape(seat_role.replace("_", " "))} seat on CookCredit.</p>'
                          f'<p><a href="{safe_url}">Accept workspace invitation</a></p>'
                          '<p>This email-bound link expires in seven days.</p>'),
        )
        response = sendgrid.SendGridAPIClient(key).send(message)
        return 200 <= int(response.status_code) < 300
    except Exception:
        log.exception('Workspace invitation email failed')
        return False


def _uuid(s):
    try:
        return uuid.UUID(str(s))
    except (ValueError, TypeError, AttributeError):
        return None


def _membership(session, user_id):
    return session.query(OrgMembership).filter_by(user_id=user_id).first()


def _org_for(session, user_id):
    m = _membership(session, user_id)
    return session.get(Org, m.org_id) if m else None


def _require_business(session, user_id):
    """True only if the user actually HOLDS the 'business' role. Org membership alone is NOT
    sufficient — activate() is self-serve, so the role is the authorization anchor for reads that
    expose the verified-cook pool (names/scores) and biometric capture."""
    user = session.get(User, user_id)
    return bool(user and "business" in (user.roles or []))


def _idlist(v, cap=30):
    return [str(x)[:60] for x in v][:cap] if isinstance(v, list) else []


def _clamp_int(v, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return None


QUESTION_TYPES = {'short_text', 'long_text', 'yes_no', 'select', 'multiselect', 'phone'}


def _questions(value):
    out, seen = [], set()
    if not isinstance(value, list):
        return out
    for raw in value[:20]:
        if not isinstance(raw, dict):
            continue
        qid = str(raw.get('id') or '').strip()[:50]
        label = re.sub(r'\s+', ' ', str(raw.get('label') or '').strip())[:160]
        kind = raw.get('type')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,49}', qid) or qid in seen or not label or kind not in QUESTION_TYPES:
            continue
        options = []
        if kind in ('select', 'multiselect'):
            options = list(dict.fromkeys(re.sub(r'\s+', ' ', str(x).strip())[:80]
                                         for x in (raw.get('options') or []) if str(x).strip()))[:20]
            if len(options) < 2:
                continue
        seen.add(qid)
        out.append({'id': qid, 'label': label, 'type': kind,
                    'required': bool(raw.get('required')), 'options': options})
    return out


def _loc(value):
    if not isinstance(value, dict):
        return None
    try:
        lat, lng = float(value.get('lat')), float(value.get('lng'))
    except (TypeError, ValueError):
        return None
    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
        return None
    return {'lat': round(lat, 6), 'lng': round(lng, 6)}


def _https_url(value, *, allow_empty=True):
    raw = str(value or '').strip()
    if not raw and allow_empty:
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
        return None
    return raw[:1000]


def _embed_origins(value):
    if not isinstance(value, list):
        raise ValueError('Allowed website origins must be a list')
    out = []
    for raw in value[:20]:
        try:
            parsed = urlsplit(str(raw).strip())
        except ValueError:
            raise ValueError('One or more website origins are invalid')
        local = parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')
        if (parsed.scheme != 'https' and not local) or not parsed.netloc or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('Use exact HTTPS origins without a path or wildcard')
        origin = f'{parsed.scheme}://{parsed.netloc}'
        if origin not in out:
            out.append(origin)
    return out


def _org_shortlist(session, org_id):
    sl = session.query(Shortlist).filter_by(org_id=org_id).first()
    if sl is None:
        sl = Shortlist(org_id=org_id, name="Shortlist")
        session.add(sl)
        session.flush()
    return sl


def _cook_facts(session, cook_id):
    """Job-related facts for the server matcher: the verified score + latest resume key-point ids."""
    cp = session.get(CookProfile, cook_id)
    rk = (session.query(ResumeKeypoints).filter_by(cook_id=cook_id)
          .order_by(ResumeKeypoints.version.desc()).first())
    pts = [p.get("canonical_id") for p in (rk.points or [])] if rk else []
    return {"verifiedScore": _score(cp), "resumePoints": [p for p in pts if p],
            "assessmentEligible": os.environ.get('ASSESSMENT_EMPLOYMENT_VALIDATED') == '1',
            "hasVideo": bool(cp and getattr(cp, "skill_test_video_url", None))}


def _assessment_report(attempt):
    """Allowlisted, explainable view of scoring evidence; excludes storage locators."""
    from services.live_motion_evidence import is_live_motion, motion_report
    if is_live_motion(attempt):
        return motion_report(attempt, (attempt.metadata_ or {}).get('assessment_criteria'))
    server = attempt.server_block if isinstance(attempt.server_block, dict) else {}
    motion = server.get("motion_half") if isinstance(server.get("motion_half"), dict) else {}
    product = server.get("product_half") if isinstance(server.get("product_half"), dict) else {}
    verdict = server.get("verdict") if isinstance(server.get("verdict"), dict) else {}
    recon = attempt.reconciliation if isinstance(attempt.reconciliation, dict) else {}
    employment_validated = os.environ.get('ASSESSMENT_EMPLOYMENT_VALIDATED') == '1'
    outcome = evaluate_assessment(
        attempt, profile_version=(attempt.metadata_ or {}).get('assessment_profile_version', 'knife-dice-v1'),
        criteria=(attempt.metadata_ or {}).get('assessment_criteria'))
    return {
        "attemptId": str(attempt.id),
        "status": "recording-analyzed" if attempt.verification_state == "VERIFIED" else attempt.verification_state.lower(),
        "score": float(attempt.authoritative_score) if attempt.authoritative_score is not None else None,
        "tier": attempt.tier,
        "profileId": attempt.profile_id,
        "recordedAt": attempt.created_at.isoformat() if attempt.created_at else None,
        "outcome": outcome,
        "measurements": {
            "motionDetected": motion.get("technique") not in (None, "uncertain"),
            "detectedTechnique": motion.get("candidate"),
            "motionCalibrationLimited": bool(motion.get("low_calibration")),
            "productGradeable": bool(product.get("ok")),
            "requestedTechniqueMatched": verdict.get("technique_ok"),
            "productScore": verdict.get("product_score"),
            "requestedProductDetected": verdict.get("is_dice"),
        },
        "calculation": {
            "scoreSource": "Video-derived product-quality composite",
            "clientScoreUsedForHiring": False,
            "comparison": "Client motion and video motion are compared only as a consistency check; their numeric scores are not combined.",
            "resultReason": recon.get("reason") or recon.get("summary") or verdict.get("summary"),
        },
        "provenance": {
            "recordingGenerationPinned": bool((attempt.metadata_ or {}).get("recording_generation")),
            "profileId": attempt.profile_id,
            "scoringSchema": (attempt.metadata_ or {}).get("schema"),
            "attemptEventsPreserved": True,
        },
        "limitations": {
            "employmentValidated": employment_validated,
            "automaticHiringDecision": False,
            "message": ("Employment-use validation is enabled for this deployment. A person must still review the evidence."
                        if employment_validated else
                        "This recorded work sample is not yet validated for automatic employment screening. Review the recording and other job evidence; do not reject a candidate from this score alone."),
        },
    }


def _cook_in_org_pipeline(session, org_id, cook_id):
    """True if the cook is in a pipeline for one of the org's roles (i.e. applied to THEM).
    Scopes video/PII access to candidates who submitted to this business — not every verified cook."""
    return (session.query(PipelineCard)
            .join(RolePosting, RolePosting.id == PipelineCard.role_posting_id)
            .filter(RolePosting.org_id == org_id, RolePosting.integration_environment == 'live',
                    PipelineCard.cook_id == cook_id)
            .first() is not None)


def _seat_role(session, user_id):
    m = _membership(session, user_id)
    return m.seat_role if m else None


def _can(session, user_id, permission):
    """Business access requires both the account role and an explicit organization seat."""
    if not _require_business(session, user_id):
        return False
    return permission in SEAT_PERMISSIONS.get(_seat_role(session, user_id), set())


def _active_share_for_org(session, org_id, cook_id, role_id=None):
    q = (session.query(AssessmentShare)
         .join(RolePosting, RolePosting.id == AssessmentShare.role_posting_id)
         .join(SkillAttempt, SkillAttempt.id == AssessmentShare.attempt_id)
         .filter(RolePosting.org_id == org_id,
                 RolePosting.integration_environment == 'live',
                 AssessmentShare.applicant_id == cook_id,
                 AssessmentShare.revoked_at.is_(None),
                 SkillAttempt.user_id == cook_id,
                 SkillAttempt.verification_state.in_(ATTEMPT_TERMINAL)))
    if role_id is not None:
        q = q.filter(AssessmentShare.role_posting_id == role_id)
    return q.order_by(AssessmentShare.granted_at.desc()).first()


def _shared_candidate(session, org_id, cook_id):
    """Candidate facts are visible only while an applicant consent grant is active."""
    return _active_share_for_org(session, org_id, cook_id) is not None


def _score(cp):
    """verified skill score as float-or-None (one place; used by the matcher + the roster)."""
    return float(cp.skill_score) if cp and cp.skill_score is not None else None


def _get_or_create_card(session, role_id, cook_id, default_stage="invited"):
    """Fetch the pipeline card for (role, cook), creating it if absent. Callers set the field."""
    card = (session.query(PipelineCard)
            .filter_by(role_posting_id=role_id, cook_id=cook_id).first())
    if card is None:
        card = PipelineCard(role_posting_id=role_id, cook_id=cook_id, stage=default_stage)
        session.add(card)
    return card


def _verified_cook(session, cook_id):
    """The CookProfile for a VERIFIED cook, else None. Guards writes that take a client-supplied
    cookId so a business can't inject arbitrary user ids into the shortlist (which would also seed
    AedtAuditLog rows via role_detail). The shortlist is, by definition, a pool of verified cooks."""
    cp = session.get(CookProfile, cook_id)
    return cp if (cp and getattr(cp, "skill_verified", False)) else None


def _cook_exists(session, cook_id):
    """True if cook_id belongs to a real COOK (a CookProfile row exists), regardless of verification
    status. Looser than _verified_cook on purpose: the pipeline legitimately holds pre-verification
    cooks (invited/assessing stages), so stage/star/notice must accept them — while still rejecting
    arbitrary user ids (eaters, other orgs' admins, random ids) that would pollute the pipeline and
    seed AedtAuditLog rows via role_detail. CookProfile's primary key IS the user id."""
    return session.get(CookProfile, cook_id) is not None


@business_bp.route("/activate", methods=["POST"])
@require_auth
@require_verified_email
@limiter.limit("10 per hour", key_func=lambda: g.user_id)
def activate():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "My kitchen").strip()[:200] or "My kitchen"
    city = (data.get("city") or "").strip()[:120] or None
    loc = data.get("loc") if isinstance(data.get("loc"), dict) else None
    focus = [str(x)[:40] for x in (data.get("cuisineFocus") or [])][:12]
    with db_session() as session:
        user = session.get(User, g.user_id)
        if user is None:
            return jsonify({"error": "User not found"}), 404
        m = _membership(session, g.user_id)
        if m:
            org = session.get(Org, m.org_id)
        else:
            org = Org(name=name, city=city, location=loc, cuisine_focus=focus, created_by=g.user_id)
            session.add(org)
            session.flush()
            session.add(OrgMembership(org_id=org.id, user_id=g.user_id, seat_role="admin"))
            session.add(Shortlist(org_id=org.id, name="Shortlist"))
        if "business" not in (user.roles or []):
            user.roles = list(user.roles or []) + ["business"]
        user.active_role = "business"
        out = org.to_dict()
        out_user = user.to_dict()   # so the client can setProfile the persisted role with no 2nd round-trip
    return jsonify({"ok": True, "org": out, "user": out_user}), 200


@business_bp.route("/org", methods=["GET"])
@require_auth
def get_org():
    with db_session() as session:
        if not _can(session, g.user_id, "workspace"):
            return jsonify({"error": "Business workspace required"}), 403
        org = _org_for(session, g.user_id)
        out = org.to_dict() if org else None
        if out:
            out['seatRole'] = _seat_role(session, g.user_id)
    return jsonify({"org": out}), 200


@business_bp.route('/org', methods=['PATCH'])
@require_auth
@require_verified_email
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def update_org():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) - {'name', 'city'}:
        return jsonify(error='Only company name and city can be changed here'), 400
    for key, maximum in (('name', 200), ('city', 120)):
        if key in data and (not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > maximum):
            return jsonify(error=f'A valid {key} is required'), 400
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can edit company details'), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify(error='Workspace not found'), 404
        for key in ('name', 'city'):
            if key in data:
                setattr(org, key, data[key].strip())
        session.flush()
        out = org.to_dict()
        out['seatRole'] = _seat_role(session, g.user_id)
    return jsonify(org=out), 200


@business_bp.route('/team', methods=['GET'])
@require_auth
def get_team():
    """Server-owned members and pending invitations; never fabricate seats in the client."""
    now = _utcnow()
    with db_session() as session:
        if not _can(session, g.user_id, 'workspace'):
            return jsonify(error='Business workspace required'), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify(members=[], invitations=[]), 200
        invitations = (session.query(OrgInvitation).filter_by(org_id=org.id)
                       .order_by(OrgInvitation.created_at.desc()).limit(100).all())
        for invitation in invitations:
            if invitation.status == 'pending' and invitation.expires_at <= now:
                invitation.status = 'expired'
        members = (session.query(OrgMembership, User)
                   .join(User, User.id == OrgMembership.user_id)
                   .filter(OrgMembership.org_id == org.id)
                   .order_by(OrgMembership.created_at, OrgMembership.id).all())
        return jsonify(
            members=[{
                'id': str(membership.id), 'userId': membership.user_id,
                'email': user.email, 'name': user.name, 'seatRole': membership.seat_role,
                'joinedAt': membership.created_at.isoformat() if membership.created_at else None,
            } for membership, user in members],
            invitations=[{
                'id': str(item.id), 'email': item.invited_email, 'seatRole': item.seat_role,
                'status': item.status, 'expiresAt': item.expires_at.isoformat(),
                'createdAt': item.created_at.isoformat() if item.created_at else None,
            } for item in invitations],
            canManage=_can(session, g.user_id, 'billing'),
        ), 200


@business_bp.route('/team/invitations', methods=['POST'])
@require_auth
@limiter.limit('20 per hour', key_func=lambda: g.user_id)
def invite_team_member():
    body = request.get_json(silent=True) or {}
    email = str(body.get('email') or '').strip().casefold()[:320]
    seat_role = str(body.get('seatRole') or '').strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        return jsonify(error='A valid email address is required'), 400
    if seat_role not in SEAT_ROLES:
        return jsonify(error='Invalid seat role'), 400
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = _utcnow()
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can invite team members'), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify(error='Workspace not found'), 404
        if org.plan not in ('team', 'integration', 'enterprise'):
            return jsonify(error='Team seats require a paid subscription'), 402
        existing_user = session.query(User).filter(User.email.ilike(email)).one_or_none()
        if existing_user and session.query(OrgMembership).filter_by(
                org_id=org.id, user_id=existing_user.id).first():
            return jsonify(error='This person is already a workspace member'), 409
        pending = (session.query(OrgInvitation).filter(
            OrgInvitation.org_id == org.id,
            OrgInvitation.invited_email == email,
            OrgInvitation.status == 'pending').with_for_update().one_or_none())
        if pending and pending.expires_at > now:
            return jsonify(error='A current invitation already exists for this email'), 409
        if pending:
            pending.status = 'expired'
            session.flush()
        invitation = OrgInvitation(
            org_id=org.id, invited_email=email, seat_role=seat_role,
            token_hash=token_hash, status='pending', invited_by=g.user_id,
            expires_at=now + timedelta(days=7))
        session.add(invitation)
        session.flush()
        invitation_id, expires_at, org_name = str(invitation.id), invitation.expires_at, org.name
    origin = os.environ.get('FRONTEND_URL', 'http://localhost:5173').split(',', 1)[0].rstrip('/')
    invite_url = f'{origin}/business/invite/{token}'
    emailed = _send_workspace_invite(
        recipient=email, org_name=org_name, seat_role=seat_role, invite_url=invite_url)
    return jsonify(invitation={
        'id': invitation_id, 'email': email, 'seatRole': seat_role,
        'status': 'pending', 'expiresAt': expires_at.isoformat(),
        'inviteUrl': invite_url, 'emailDelivered': emailed,
    }), 201


@business_bp.route('/team/invitations/<invitation_id>/revoke', methods=['POST'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def revoke_team_invitation(invitation_id):
    iid = _uuid(invitation_id)
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can revoke invitations'), 403
        org = _org_for(session, g.user_id)
        item = (session.query(OrgInvitation).filter_by(id=iid, org_id=org.id)
                .with_for_update().one_or_none()) if iid and org else None
        if not item:
            return jsonify(error='Not found'), 404
        if item.status == 'pending':
            item.status = 'revoked'
        return jsonify(ok=True, status=item.status), 200


@business_bp.route('/team/invitations/accept', methods=['POST'])
@require_auth
@limiter.limit('10 per hour', key_func=lambda: g.user_id)
def accept_team_invitation():
    raw_token = str((request.get_json(silent=True) or {}).get('token') or '').strip()
    if not raw_token or not g.email_verified:
        return jsonify(error='A verified email and valid invitation are required'), 403
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = _utcnow()
    with db_session() as session:
        item = (session.query(OrgInvitation).filter_by(token_hash=token_hash)
                .with_for_update().one_or_none())
        if not item or item.status not in ('pending', 'accepted'):
            return jsonify(error='This invitation is invalid or no longer active'), 409
        if item.expires_at <= now:
            item.status = 'expired'
            return jsonify(error='This invitation has expired'), 409
        if item.invited_email != str(g.email or '').casefold():
            return jsonify(error='Sign in with the email address that received this invitation'), 403
        existing = _membership(session, g.user_id)
        if existing and existing.org_id != item.org_id:
            return jsonify(error='This account already belongs to another workspace'), 409
        if not existing:
            session.add(OrgMembership(org_id=item.org_id, user_id=g.user_id, seat_role=item.seat_role))
        user = session.get(User, g.user_id)
        if not user:
            return jsonify(error='User not found'), 404
        if 'business' not in (user.roles or []):
            user.roles = list(user.roles or []) + ['business']
        item.status = 'accepted'; item.accepted_by = g.user_id; item.accepted_at = now
        org = session.get(Org, item.org_id)
        return jsonify(ok=True, org=org.to_dict(), seatRole=item.seat_role), 200


@business_bp.route('/integrations', methods=['PATCH'])
@require_auth
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def update_integrations():
    data = request.get_json(silent=True) or {}
    color = str(data.get('color') or '').strip().upper()
    if not re.fullmatch(r'#[0-9A-F]{6}', color):
        return jsonify(error='Brand color must be a six-digit hex value'), 400
    raw_logo = data.get('logoUrl')
    logo = _https_url(raw_logo)
    if raw_logo and not logo:
        return jsonify(error='Logo must use an HTTPS URL'), 400
    try:
        origins = _embed_origins(data.get('allowedOrigins') or [])
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can manage integrations'), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify(error='Workspace not found'), 404
        org.brand_color = color
        org.brand_logo_url = logo
        org.embed_allowed_origins = origins
        if not org.public_embed_key:
            org.public_embed_key = 'pk_' + secrets.token_urlsafe(24)
        session.flush()
        out = org.to_dict()
    return jsonify(org=out), 200


@business_bp.route('/integrations/logo', methods=['POST', 'DELETE'])
@require_auth
@require_verified_email
@limiter.limit('20 per hour', key_func=lambda: g.user_id)
def company_logo():
    request.max_content_length = 3 * 1024 * 1024
    with db_session() as session:
        if not _can(session, g.user_id, 'billing'):
            return jsonify(error='Only a workspace admin can change the company logo'), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify(error='Workspace not found'), 404
        session.refresh(org, with_for_update=True)
        if request.method == 'DELETE':
            org.brand_logo_url = None
        else:
            uploaded = request.files.get('logo')
            if uploaded is None:
                return jsonify(error='Choose a logo image to upload'), 400
            try:
                encoded = company_branding.normalize_logo(uploaded.stream.read(company_branding.MAX_LOGO_BYTES + 1))
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
            try:
                digest = company_branding.store_logo(str(org.id), encoded)
            except Exception:
                log.exception('Company logo storage failed')
                return jsonify(error='The logo could not be saved. Please try again.'), 503
            origin = os.environ.get('PUBLIC_API_URL', request.url_root).rstrip('/')
            org.brand_logo_url = f'{origin}/api/business/branding/{org.id}/{digest}.png'
        session.flush()
        return jsonify(org=org.to_dict()), 200


@business_bp.route('/branding/<org_id>/<digest>.png', methods=['GET'])
@limiter.limit('120 per minute')
def public_company_logo(org_id, digest):
    oid = _uuid(org_id)
    if not oid or not re.fullmatch(r'[0-9a-f]{64}', digest):
        return jsonify(error='Logo not found'), 404
    # Only the currently published logo is public. Never accept a storage path.
    with db_session() as session:
        org = session.get(Org, oid)
        expected_path = f'/api/business/branding/{oid}/{digest}.png'
        if not org or urlsplit(org.brand_logo_url or '').path != expected_path:
            return jsonify(error='Logo not found'), 404
    try:
        data = company_branding.read_logo(str(oid), digest)
    except Exception:
        log.warning('Company logo unavailable', exc_info=True)
        return jsonify(error='Logo unavailable'), 404
    response = make_response(data)
    response.headers['Content-Type'] = 'image/png'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'public, max-age=300'
    response.set_etag(digest)
    return response.make_conditional(request)


@business_bp.route("/roles", methods=["GET"])
@require_auth
def list_roles():
    with db_session() as session:
        if not _can(session, g.user_id, "workspace"):
            return jsonify({"error": "Business workspace required"}), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify({"roles": []}), 200
        roles = (session.query(RolePosting).filter_by(org_id=org.id)
                 .filter(RolePosting.integration_managed.is_(False))
                 .order_by(RolePosting.created_at.desc()).all())
        out = [r.to_dict() for r in roles]
    return jsonify({"roles": out}), 200


@business_bp.route("/roles", methods=["POST"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def create_role():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()[:200]
    if not title:
        return jsonify({"error": "Title required"}), 400
    location_label = re.sub(r'\s+', ' ', str(data.get('locationLabel') or '').strip())[:160] or None
    raw_questions = data.get('applicationQuestions') or []
    questions = _questions(raw_questions)
    if not isinstance(raw_questions, list) or len(questions) != len(raw_questions):
        return jsonify(error='One or more application questions are invalid'), 400
    try:
        instructions = assessment_instructions(data.get('assessmentInstructions'))
        criteria = hiring_motion_criteria(data.get('assessmentCriteria'), skill_floor=data.get('skillFloor'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    requirements = {
        'assessmentCriteria': criteria,
        'assessmentInstructions': instructions,
        "required": _idlist(data.get("required")),
        "preferred": _idlist(data.get("preferred")),
        "skillFloor": _clamp_int(data.get("skillFloor"), 0, 100),
        "certsRequired": _idlist(data.get("certsRequired")),
        "cuisines": _idlist(data.get("cuisines")),
        "loc": _loc(data.get("loc")),
        "radiusM": _clamp_int(data.get("radiusM"), 0, 500000),
        "locationLabel": location_label,
        "workMode": data.get('workMode') if data.get('workMode') in ('onsite', 'hybrid') else 'onsite',
        "applicationQuestions": questions,
        "attemptLimit": _clamp_int(data.get('attemptLimit'), 1, 3) or 3,
        "role": str(data.get('role') or '')[:60] or None,
        "station": str(data.get('station') or '')[:80] or None,
        "employmentType": str(data.get('employmentType') or '')[:80] or None,
        "shifts": _idlist(data.get('shifts'), cap=20),
        "payMin": _clamp_int(data.get('payMin'), 0, 10000),
        "payMax": _clamp_int(data.get('payMax'), 0, 10000),
        "tips": bool(data.get('tips')),
        "experience": str(data.get('experience') or '')[:80] or None,
        "mustHave": _idlist(data.get('mustHave'), cap=5),
        "physical": _idlist(data.get('physical'), cap=20),
        "softSkills": _idlist(data.get('softSkills'), cap=20),
        "description": str(data.get('description') or '').strip()[:2000] or None,
    }
    if requirements['payMin'] is not None and requirements['payMax'] is not None and requirements['payMin'] > requirements['payMax']:
        return jsonify(error='Pay minimum cannot exceed pay maximum'), 400
    status = data.get("status") if data.get("status") in ("draft", "open", "closed") else "open"
    if status == 'open' and not location_label:
        return jsonify(error='Work location required for an open role'), 400
    with db_session() as session:
        if not _can(session, g.user_id, "roles"):
            return jsonify({"error": "This seat cannot create roles"}), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify({"error": "Activate a workspace first"}), 400
        # Serialize quota checks for this workspace, including simultaneous publications.
        org = session.query(Org).filter_by(id=org.id).populate_existing().with_for_update().one()
        role_limit = open_role_limit(org)
        if status == 'open' and role_limit is not None:
            open_roles = (session.query(RolePosting).filter_by(org_id=org.id, status='open')
                          .filter(RolePosting.integration_managed.is_(False)).count())
            if open_roles >= role_limit:
                message = ('Free early access includes five open roles' if role_limit == 5
                           else 'The trial includes one open role')
                return jsonify(error=message, code='open_role_limit_reached',
                               openRoleLimit=role_limit, upgradeRequired=role_limit == 1), 409
        r = RolePosting(org_id=org.id, title=title, status=status,
                        requirements=requirements, created_by=g.user_id)
        session.add(r)
        session.flush()
        out = r.to_dict()
    return jsonify({"role": out}), 201


def _role_owned(session, rid, user_id):
    ru = _uuid(rid)
    org = _org_for(session, user_id)
    if not ru or not org:
        return None
    r = session.get(RolePosting, ru)
    return r if (r and r.org_id == org.id and r.integration_environment == 'live') else None


@business_bp.route('/role/<rid>/status', methods=['POST'])
@require_auth
@require_verified_email
@limiter.limit('30 per hour', key_func=lambda: g.user_id)
def change_role_status(rid):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {'status'} or data['status'] not in ('open', 'closed'):
        return jsonify(error='Choose open or closed'), 400
    with db_session() as session:
        if not _can(session, g.user_id, 'roles'):
            return jsonify(error='This seat cannot manage roles'), 403
        role = _role_owned(session, rid, g.user_id)
        if not role:
            return jsonify(error='Not found'), 404
        if role.integration_managed:
            return jsonify(error='Manage this role through its integration'), 409
        # Same workspace lock/order as publication: reopening must not bypass quota.
        org = session.query(Org).filter_by(id=role.org_id).with_for_update().one()
        role = session.query(RolePosting).filter_by(id=role.id).populate_existing().with_for_update().one()
        target = data['status']
        if target == 'open' and role.status != 'open':
            if not (role.requirements or {}).get('locationLabel'):
                return jsonify(error='Work location required for an open role'), 400
            limit = open_role_limit(org)
            opened = session.query(RolePosting).filter_by(org_id=org.id, status='open', integration_managed=False).count()
            if limit is not None and opened >= limit:
                return jsonify(error='Your open-role limit has been reached. Close another role first.',
                               code='open_role_limit_reached', openRoleLimit=limit), 409
        role.status = target
        session.flush()
        result = role.to_dict()
    return jsonify(role=result), 200


@business_bp.route("/role/<rid>", methods=["GET"])
@require_auth
def role_detail(rid):
    with db_session() as session:
        if not _can(session, g.user_id, "candidates"):
            return jsonify({"error": "This seat cannot review candidates"}), 403
        r = _role_owned(session, rid, g.user_id)
        if not r:
            return jsonify({"error": "Not found"}), 404
        role_dict = r.to_dict()
        req = r.requirements or {}
        requirement_set = {
            "required": role_dict.get("required"), "preferred": role_dict.get("preferred"),
            "certsRequired": role_dict.get("certsRequired"), "mustHave": req.get("mustHave"),
            "skillFloor": role_dict.get("skillFloor"),
        }
        cards_out = []
        for c in session.query(PipelineCard).filter_by(role_posting_id=r.id).all():
            if not _shared_candidate(session, r.org_id, c.cook_id):
                continue
            cook = _cook_facts(session, c.cook_id)
            m = match_role(cook, {**role_dict, "mustHave": req.get("mustHave")})
            # Server-of-record: freeze the match on the card and append an AEDT audit row, but only
            # when the scored OUTCOME changed (no duplicate rows for an unchanged re-view).
            if (c.match_snapshot or {}).get("total") != m["total"]:
                c.match_snapshot = {"total": m["total"], "band": m["band"],
                                    "reqMet": m["reqMet"], "reqTotal": m["reqTotal"], "gates": m["gates"]}
                session.add(AedtAuditLog(
                    candidate_id=c.cook_id, role_posting_id=r.id, requirement_set=requirement_set,
                    feature_weights=FEATURE_WEIGHTS, hard_gate_outcomes=m["gates"],
                    match_total=m["total"], surface="b2b"))
            cd = c.to_dict()
            cd["hasVideo"] = cook.get("hasVideo")
            cd["match"] = {"percent": m["percent"], "band": m["band"], "reqMet": m["reqMet"],
                           "reqTotal": m["reqTotal"], "requirements": m["requirements"], "gates": m["gates"]}
            cards_out.append(cd)
        out = {"role": role_dict, "pipeline": cards_out}
    return jsonify(out), 200


@business_bp.route("/role/<rid>/stage", methods=["POST"])
@require_auth
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def move_stage(rid):
    data = request.get_json(silent=True) or {}
    cook_id = (data.get("cookId") or "").strip()
    stage = data.get("stage")
    if not cook_id or stage not in STAGES:
        return jsonify({"error": "cookId and a valid stage are required"}), 400
    with db_session() as session:
        if not _can(session, g.user_id, "decisions"):
            return jsonify({"error": "This seat cannot update hiring stages"}), 403
        r = _role_owned(session, rid, g.user_id)
        if not r:
            return jsonify({"error": "Not found"}), 404
        # Serialize board moves with application reviews; neither may silently
        # overwrite the other reviewer's revision. Published updates stay explicit.
        application = (session.query(HiringApplication)
                       .filter_by(role_posting_id=r.id, applicant_id=cook_id)
                       .with_for_update().one_or_none())
        card = (session.query(PipelineCard)
                .filter_by(role_posting_id=r.id, cook_id=cook_id).one_or_none())
        if card is None:
            return jsonify({"error": "Candidate has not applied to this role"}), 404
        if not _shared_candidate(session, r.org_id, cook_id):
            return jsonify({"error": "Candidate access is no longer active"}), 403
        if application:
            from services.hiring_consent import APPLICATION_CONSENT_VERSION
            if application.status == 'withdrawn' or application.consent_version != APPLICATION_CONSENT_VERSION:
                return jsonify(error='Candidate access is no longer active'), 403
            events = hiring_reviews.latest_events(session, application.id)
            detail = dict(events[0].detail) if events else {'notes': '', 'message': ''}
            detail['status'] = stage if stage in hiring_reviews.STATES else 'reviewing'
            if not events or detail != events[0].detail:
                session.add(HiringApplicationEvent(application_id=application.id, actor_id=g.user_id,
                    event_type=hiring_reviews.EVENTS[0], detail=detail))
        card.stage = stage
    return jsonify({"ok": True}), 200


@business_bp.route("/role/<rid>/star", methods=["POST"])
@require_auth
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def star_card(rid):
    data = request.get_json(silent=True) or {}
    cook_id = (data.get("cookId") or "").strip()
    with db_session() as session:
        if not _can(session, g.user_id, "decisions"):
            return jsonify({"error": "This seat cannot update candidates"}), 403
        r = _role_owned(session, rid, g.user_id)
        if not r or not cook_id:
            return jsonify({"error": "Not found"}), 404
        card = (session.query(PipelineCard)
                .filter_by(role_posting_id=r.id, cook_id=cook_id).one_or_none())
        if card is None or not _shared_candidate(session, r.org_id, cook_id):
            return jsonify({"error": "Candidate has not applied to this role"}), 404
        card.starred = not bool(card.starred)
        starred = card.starred
    return jsonify({"ok": True, "starred": bool(starred)}), 200


@business_bp.route("/shortlist", methods=["GET"])
@require_auth
def get_shortlist():
    with db_session() as session:
        if not _can(session, g.user_id, "candidates"):
            return jsonify({"error": "This seat cannot review candidates"}), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify({"cookIds": []}), 200
        sl = _org_shortlist(session, org.id)
        members = session.query(ShortlistMember).filter_by(shortlist_id=sl.id).all()
        out = [m.cook_id for m in members if _shared_candidate(session, org.id, m.cook_id)]
    return jsonify({"cookIds": out}), 200


@business_bp.route("/shortlist", methods=["POST"])
@require_auth
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def toggle_shortlist():
    data = request.get_json(silent=True) or {}
    cook_id = (data.get("cookId") or "").strip()
    if not cook_id:
        return jsonify({"error": "cookId required"}), 400
    with db_session() as session:
        if not _can(session, g.user_id, "decisions"):
            return jsonify({"error": "This seat cannot update candidates"}), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify({"error": "Activate a workspace first"}), 400
        if not _cook_exists(session, cook_id) or not _shared_candidate(session, org.id, cook_id):
            return jsonify({"error": "Candidate has not shared an assessment with this company"}), 403
        sl = _org_shortlist(session, org.id)
        member = (session.query(ShortlistMember)
                  .filter_by(shortlist_id=sl.id, cook_id=cook_id).first())
        if member:
            session.delete(member)
            on = False
        else:
            session.add(ShortlistMember(shortlist_id=sl.id, cook_id=cook_id))
            on = True
    return jsonify({"ok": True, "shortlisted": on}), 200


@business_bp.route("/candidates", methods=["GET"])
@require_auth
def candidates():
    """Consent-scoped candidate roster. Never exposes the global cook directory."""
    with db_session() as session:
        if not _can(session, g.user_id, "candidates"):
            return jsonify({"error": "This seat cannot review candidates"}), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify({"error": "Business workspace required"}), 403
        # One row per applicant, derived only from evidence shared with this org.
        # A global CookProfile score may belong to another unshared assessment.
        latest = (session.query(AssessmentShare.applicant_id.label('applicant_id'),
                               SkillAttempt.id.label('attempt_id'))
                  .join(RolePosting, RolePosting.id == AssessmentShare.role_posting_id)
                  .join(SkillAttempt, SkillAttempt.id == AssessmentShare.attempt_id)
                  .filter(RolePosting.org_id == org.id, RolePosting.integration_environment == 'live',
                          AssessmentShare.revoked_at.is_(None),
                          SkillAttempt.user_id == AssessmentShare.applicant_id,
                          SkillAttempt.verification_state.in_(ATTEMPT_TERMINAL))
                  .distinct(AssessmentShare.applicant_id)
                  .order_by(AssessmentShare.applicant_id, SkillAttempt.created_at.desc(), SkillAttempt.id.desc())
                  .subquery())
        rows = (session.query(CookProfile, User, SkillAttempt)
                .join(User, User.id == CookProfile.user_id)
                .join(latest, latest.c.applicant_id == User.id)
                .join(SkillAttempt, SkillAttempt.id == latest.c.attempt_id)
                .order_by(SkillAttempt.created_at.desc(), User.id).limit(200).all())
        out = []
        for cp, u, attempt in rows:
            evidence = _assessment_report(attempt)
            out.append({
                'id': u.id, 'name': u.name, 'verifiedScore': evidence['score'],
                'tier': evidence['tier'], 'cuisines': cp.cuisines or [],
                'city': cp.base_city, 'years': cp.years_experience, 'hasVideo': True,
                'assessmentStatus': evidence['status'],
            })
    employment_validated = os.environ.get('ASSESSMENT_EMPLOYMENT_VALIDATED') == '1'
    return jsonify({
        "candidates": out,
        "scope": "active-applicant-consent",
        "screeningPolicy": {
            "assessmentEmploymentValidated": employment_validated,
            "automaticRankingEnabled": employment_validated,
            "humanDecisionRequired": True,
            "scoreOnlyRejectionAllowed": False,
        },
    }), 200


def _shared_attempt_order():
    """Use the same deterministic assessment order for reports and legacy playback."""
    return (SkillAttempt.created_at.desc().nullslast(), SkillAttempt.id.desc(), AssessmentShare.id.desc())


@business_bp.route("/candidate/<cook_id>/video", methods=["GET"])
@require_auth
@limiter.limit("60 per hour", key_func=lambda: g.user_id)
def candidate_video(cook_id):
    """Issue short-lived playback only for an applicant-approved assessment share."""
    attempt_id = None
    if 'attemptId' in request.args:
        attempt_id = _uuid(request.args['attemptId'])
        if attempt_id is None:
            return jsonify(error='Invalid assessment attempt'), 400
    with db_session() as session:
        org = _org_for(session, g.user_id)
        if not (_can(session, g.user_id, "evidence") and org):
            return jsonify({"error": "Business workspace required"}), 403
        query = (session.query(AssessmentShare)
                 .join(RolePosting, RolePosting.id == AssessmentShare.role_posting_id)
                 .join(SkillAttempt, SkillAttempt.id == AssessmentShare.attempt_id)
                 .filter(RolePosting.org_id == org.id,
                         RolePosting.integration_environment == 'live',
                         AssessmentShare.applicant_id == cook_id,
                         SkillAttempt.user_id == cook_id,
                         SkillAttempt.verification_state.in_(ATTEMPT_TERMINAL),
                         AssessmentShare.revoked_at.is_(None)))
        if request.args.get('roleId'):
            rid = _uuid(request.args['roleId'])
            if not rid:
                return jsonify(error='Invalid role'), 400
            query = query.filter(AssessmentShare.role_posting_id == rid)
        if attempt_id is not None:
            query = query.filter(AssessmentShare.attempt_id == attempt_id)
        # Never fall back to another attempt when the displayed report's share
        # is missing or revoked. Older callers without an ID use report ordering.
        # Serialize grant issuance with revocation. A revoke that completes first
        # prevents issuance; an already issued URL has a bounded five-minute life.
        grant = query.order_by(*_shared_attempt_order()).with_for_update(of=AssessmentShare).first()
        if not grant:
            return jsonify(error='The applicant has not shared an assessment with this company'), 403
        original_url = None
        try:
            url = playback_url(grant.storage_path, grant.storage_generation, cook_id)
            if request.args.get('landmarks') == '1':
                attempt = session.get(SkillAttempt, grant.attempt_id)
                original_url = landmarks_url((attempt.metadata_ or {}).get('original_landmarks'),
                                             grant.storage_path, grant.storage_generation)
        except Exception:
            return jsonify(error='Recording playback is temporarily unavailable'), 503
        session.add(AssessmentAccessLog(share_id=grant.id, viewer_id=g.user_id))
        shared_attempt = str(grant.attempt_id)
    response = jsonify(videoUrl=url, landmarksUrl=original_url, attemptId=shared_attempt, expiresInSeconds=PLAYBACK_TTL_SECONDS)
    response.headers['Cache-Control'] = 'no-store'
    return response, 200


@business_bp.route('/candidate/<cook_id>/report', methods=['GET'])
@require_auth
@limiter.limit('120 per hour', key_func=lambda: g.user_id)
def candidate_report(cook_id):
    """Consent-scoped facts, history and explanations for human hiring review."""
    with db_session() as session:
        org = _org_for(session, g.user_id)
        if not (_can(session, g.user_id, 'candidates') and org):
            return jsonify(error='This seat cannot review candidates'), 403
        rid = _uuid(request.args.get('roleId')) if request.args.get('roleId') else None
        if request.args.get('roleId') and rid is None:
            return jsonify(error='Invalid role'), 400
        if rid is not None:
            role = session.get(RolePosting, rid)
            if role is None or role.org_id != org.id or role.integration_environment != 'live':
                return jsonify(error='Not found'), 404
        share_query = (session.query(AssessmentShare, SkillAttempt, RolePosting)
                       .join(SkillAttempt, SkillAttempt.id == AssessmentShare.attempt_id)
                       .join(RolePosting, RolePosting.id == AssessmentShare.role_posting_id)
                       .filter(RolePosting.org_id == org.id,
                               RolePosting.integration_environment == 'live',
                               AssessmentShare.applicant_id == cook_id,
                               AssessmentShare.revoked_at.is_(None),
                               SkillAttempt.user_id == cook_id,
                               SkillAttempt.verification_state.in_(ATTEMPT_TERMINAL)))
        if rid is not None:
            share_query = share_query.filter(AssessmentShare.role_posting_id == rid)
        shared = share_query.order_by(*_shared_attempt_order()).all()
        if not shared:
            return jsonify(error='The applicant has not shared an assessment with this company'), 404
        user, cp = session.get(User, cook_id), session.get(CookProfile, cook_id)
        if not user or not cp:
            return jsonify(error='Not found'), 404
        rk = (session.query(ResumeKeypoints).filter_by(cook_id=cook_id)
              .order_by(ResumeKeypoints.version.desc()).first())
        resume_points = [p.get('canonical_id') for p in (rk.points or [])
                         if isinstance(p, dict) and p.get('canonical_id')] if rk else []
        selected_role = shared[0][2]
        facts = _cook_facts(session, cook_id)
        role_for_match = selected_role.to_dict()
        role_for_match['mustHave'] = (selected_role.requirements or {}).get('mustHave', [])
        match = match_role(facts, role_for_match) if rid else None
        reports = [_assessment_report(attempt) for _, attempt, _ in shared]
        return jsonify({
            'candidate': {
                'id': user.id, 'name': user.name, 'photo': user.photo_url,
                'bio': cp.bio, 'cuisines': cp.cuisines or [], 'city': cp.base_city,
                'years': cp.years_experience, 'resumePoints': resume_points,
            },
            'role': {'id': str(selected_role.id), 'title': selected_role.title} if rid else None,
            'assessment': reports[0],
            'attemptHistory': reports,
            'match': match,
            'reviewPolicy': {
                'humanDecisionRequired': True,
                'scoreOnlyRejectionAllowed': False,
                'alternativeAssessmentAvailable': True,
                'candidateCanRevokeFutureEvidenceAccess': True,
            },
        }), 200


@business_bp.route("/role/<rid>/notice", methods=["POST"])
@require_auth
@limiter.limit("120 per hour", key_func=lambda: g.user_id)
def record_notice(rid):
    """Employer records an LL144 candidate notice (what is assessed, when) for a cook in the role."""
    data = request.get_json(silent=True) or {}
    cook_id = (data.get("cookId") or "").strip()
    with db_session() as session:
        if not _can(session, g.user_id, "decisions"):
            return jsonify({"error": "This seat cannot manage candidate notices"}), 403
        r = _role_owned(session, rid, g.user_id)
        if not r or not cook_id:
            return jsonify({"error": "Not found"}), 404
        card = (session.query(PipelineCard)
                .filter_by(role_posting_id=r.id, cook_id=cook_id).one_or_none())
        if card is None:
            return jsonify({"error": "Candidate has not applied to this role"}), 404
        session.add(CandidateNotice(
            cook_id=cook_id, role_posting_id=r.id,
            qualifications=data.get("qualifications") if isinstance(data.get("qualifications"), dict) else None,
            method=data.get("method") if data.get("method") in ("in_app", "email") else "in_app"))
    return jsonify({"ok": True}), 200


@business_bp.route("/opt-out", methods=["POST"])
@require_auth
@limiter.limit("10 per hour", key_func=lambda: g.user_id)
def opt_out():
    """Candidate-facing: request the alternative / human-review process (LL144 + ADA)."""
    data = request.get_json(silent=True) or {}
    with db_session() as session:
        session.add(OptOutRequest(
            cook_id=g.user_id, role_posting_id=_uuid(data.get("roleId")),
            reason=(data.get("reason") or "")[:1000]))
    return jsonify({"ok": True, "message": "Request received — a person will review."}), 200


@business_bp.route("/plan", methods=["POST"])
@require_auth
@limiter.limit("20 per hour", key_func=lambda: g.user_id)
def set_plan():
    """Paid entitlements are webhook-owned; a browser cannot grant its own plan."""
    data = request.get_json(silent=True) or {}
    plan = data.get("plan")
    if plan not in ("trial", "team", "integration", "enterprise"):
        return jsonify({"error": "Unknown plan"}), 400
    with db_session() as session:
        if not _can(session, g.user_id, "billing"):
            return jsonify({"error": "Only a workspace admin can manage billing"}), 403
        org = _org_for(session, g.user_id)
        if not org:
            return jsonify({"error": "Business workspace required"}), 403
        if plan in ("team", "integration"):
            return jsonify(error='Paid plans require Stripe Checkout and a verified webhook'), 409
        if plan == "trial" and org.plan != "trial":
            return jsonify(error='Use the billing portal to change an active subscription'), 409
        out = org.to_dict()
        contact_sales = plan == "enterprise"     # enterprise: interest only, no self-activation
    body = {"ok": True, "org": out}
    if contact_sales:
        body.update(contactSales=True, message="Enterprise is sales-assisted — we’ll reach out.")
    return jsonify(body), 200
