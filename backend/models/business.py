"""
B2B hiring models — org workspace, role postings (scorecards), candidate pipeline, shortlists,
parsed resume key-points, and the AEDT audit log. Map 1:1 to migrations/002_business.sql.

Geo is stored as JSONB {lat,lng} for now (the match/proximity math lives in the ranker);
PostGIS GEOGRAPHY + ST_DWithin geo-fencing is a later migration.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, Numeric, Boolean, Date, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ARRAY
import uuid

from services.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Org(Base):
    __tablename__ = "orgs"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    city = Column(Text)
    location = Column(JSONB)                       # {lat, lng}
    cuisine_focus = Column(ARRAY(Text), default=list)
    plan = Column(Text, default="trial")           # trial | team | integration | enterprise
    stripe_customer_id = Column(Text, unique=True)
    stripe_subscription_id = Column(Text, unique=True)
    subscription_status = Column(Text)
    subscription_price_id = Column(Text)
    subscription_period_end = Column(DateTime(timezone=True))
    subscription_cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    billing_updated_at = Column(DateTime(timezone=True))
    brand_logo_url = Column(Text)
    brand_color = Column(Text, nullable=False, default='#1F6F5C')
    embed_allowed_origins = Column(ARRAY(Text), nullable=False, default=list)
    public_embed_key = Column(Text, unique=True)
    created_by = Column(Text, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self):
        from services.integration_access import integration_access
        return {"id": str(self.id), "name": self.name, "city": self.city,
                "loc": self.location, "cuisineFocus": self.cuisine_focus or [],
                "plan": self.plan or "trial",
                "integrationAccess": integration_access(self),
                "billing": {
                    "status": self.subscription_status,
                    "cancelAtPeriodEnd": bool(self.subscription_cancel_at_period_end),
                    "periodEnd": self.subscription_period_end.isoformat() if self.subscription_period_end else None,
                },
                "branding": {"logoUrl": self.brand_logo_url, "color": self.brand_color or '#1F6F5C'},
                "embed": {"key": self.public_embed_key, "allowedOrigins": self.embed_allowed_origins or []}}


class StripeEvent(Base):
    """Processed Stripe event ids. The unique primary key makes webhooks idempotent."""
    __tablename__ = 'stripe_events'
    id = Column(Text, primary_key=True)
    event_type = Column(Text, nullable=False)
    livemode = Column(Boolean, nullable=False, default=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    processed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class OrgAssessmentUsage(Base):
    """Monthly assessment-request usage for subscription enforcement and billing support."""
    __tablename__ = 'org_assessment_usage'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey('orgs.id', ondelete='CASCADE'), nullable=False)
    period_start = Column(Date, nullable=False)
    environment = Column(Text, nullable=False, default='live')
    request_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint('org_id', 'period_start', 'environment', name='uq_org_assessment_usage_period'),
        Index('idx_org_assessment_usage_org_period', 'org_id', 'environment', 'period_start'),
    )


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_org_member"),)
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"))
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    seat_role = Column(Text, default="admin")      # admin | recruiter | hiring_manager | viewer
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class OrgInvitation(Base):
    """Email-bound, expiring invitation to a workspace seat."""
    __tablename__ = "org_invitations"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    invited_email = Column(Text, nullable=False)
    seat_role = Column(Text, nullable=False)
    token_hash = Column(Text, nullable=False, unique=True)
    status = Column(Text, nullable=False, default="pending")
    invited_by = Column(Text, ForeignKey("users.id", ondelete="SET NULL"))
    accepted_by = Column(Text, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True))

    __table_args__ = (Index("idx_org_invitations_org_status", "org_id", "status", "created_at"),)


class RolePosting(Base):
    __tablename__ = "role_postings"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"))
    title = Column(Text, nullable=False)
    status = Column(Text, default="open")          # draft | open | closed
    requirements = Column(JSONB, default=dict)     # {required[], preferred[], skillFloor, certsRequired[], cuisines[], loc, radiusM}
    external_job_id = Column(Text)
    integration_managed = Column(Boolean, nullable=False, default=False)
    integration_environment = Column(Text, nullable=False, default='live')
    created_by = Column(Text, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self):
        r = self.requirements or {}
        return {"id": str(self.id), "title": self.title, "status": self.status,
                "integrationManaged": bool(self.integration_managed),
                "required": r.get("required", []), "preferred": r.get("preferred", []),
                "skillFloor": r.get("skillFloor"), "certsRequired": r.get("certsRequired", []),
                "cuisines": r.get("cuisines", []), "loc": r.get("loc"), "radiusM": r.get("radiusM"),
                "locationLabel": r.get("locationLabel"), "workMode": r.get("workMode", "onsite"),
                "applicationQuestions": r.get("applicationQuestions", []),
                "attemptLimit": r.get("attemptLimit", 3),
                "assessmentCriteria": r.get("assessmentCriteria"),
                "role": r.get("role"), "station": r.get("station"),
                "employmentType": r.get("employmentType"), "shifts": r.get("shifts", []),
                "payMin": r.get("payMin"), "payMax": r.get("payMax"), "tips": bool(r.get("tips")),
                "experience": r.get("experience"), "mustHave": r.get("mustHave", []),
                "physical": r.get("physical", []), "softSkills": r.get("softSkills", []),
                "description": r.get("description")}


class PipelineCard(Base):
    __tablename__ = "pipeline_cards"
    __table_args__ = (UniqueConstraint("role_posting_id", "cook_id", name="uq_pipeline_card"),)
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_posting_id = Column(PG_UUID(as_uuid=True), ForeignKey("role_postings.id", ondelete="CASCADE"))
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    stage = Column(Text, default="invited")        # invited|assessing|verified|shortlisted|contacted|hired
    match_snapshot = Column(JSONB)                 # frozen match {total, requirements, ...} for audit
    starred = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def to_dict(self):
        return {"roleId": str(self.role_posting_id), "cookId": self.cook_id,
                "stage": self.stage, "starred": bool(self.starred)}


class Shortlist(Base):
    __tablename__ = "shortlists"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"))
    name = Column(Text, default="Shortlist")
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class ShortlistMember(Base):
    __tablename__ = "shortlist_members"
    __table_args__ = (UniqueConstraint("shortlist_id", "cook_id", name="uq_shortlist_member"),)
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shortlist_id = Column(PG_UUID(as_uuid=True), ForeignKey("shortlists.id", ondelete="CASCADE"))
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    added_at = Column(DateTime(timezone=True), default=_utcnow)


class ResumeKeypoints(Base):
    __tablename__ = "resume_keypoints"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    version = Column(Integer, default=1)
    points = Column(JSONB, default=list)           # [{canonical_id,label,category,evidence_span,confidence}]
    file_hash = Column(Text)                        # dedupe identical re-uploads
    taxonomy_version = Column(Text)
    model_version = Column(Text)
    parsed_at = Column(DateTime(timezone=True), default=_utcnow)


class AedtAuditLog(Base):
    """Written on every scored rank so the LL144 four-fifths / EEO-1 report is reconstructable."""
    __tablename__ = "aedt_audit_log"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id = Column(Text)
    role_posting_id = Column(PG_UUID(as_uuid=True), ForeignKey("role_postings.id", ondelete="SET NULL"))
    requirement_set = Column(JSONB)
    feature_weights = Column(JSONB)
    hard_gate_outcomes = Column(JSONB)              # {passed, failures[]}
    match_total = Column(Numeric(5, 4))
    surface = Column(Text)                          # 'b2b' | 'eater'
    created_at = Column(DateTime(timezone=True), default=_utcnow)


class CandidateNotice(Base):
    """LL144 candidate notice — a candidate was told an AEDT would assess them, what it measures,
    and given the ≥10-business-day window before assessment."""
    __tablename__ = "candidate_notices"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    role_posting_id = Column(PG_UUID(as_uuid=True), ForeignKey("role_postings.id", ondelete="SET NULL"))
    qualifications = Column(JSONB)                  # what is assessed + data sources
    method = Column(Text, default="in_app")        # in_app | email
    notified_at = Column(DateTime(timezone=True), default=_utcnow)


class OptOutRequest(Base):
    """A candidate's request for the alternative / human-review process (LL144 + ADA)."""
    __tablename__ = "opt_out_requests"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"))
    role_posting_id = Column(PG_UUID(as_uuid=True), ForeignKey("role_postings.id", ondelete="SET NULL"))
    reason = Column(Text)
    status = Column(Text, default="open")           # open | resolved
    requested_at = Column(DateTime(timezone=True), default=_utcnow)


class AssessmentShare(Base):
    __tablename__ = 'assessment_shares'
    __table_args__ = (UniqueConstraint('role_posting_id', 'attempt_id', name='uq_assessment_share'),)
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_posting_id = Column(PG_UUID(as_uuid=True), ForeignKey('role_postings.id', ondelete='CASCADE'), nullable=False)
    attempt_id = Column(PG_UUID(as_uuid=True), ForeignKey('skill_attempts.id', ondelete='CASCADE'), nullable=False)
    applicant_id = Column(Text, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    storage_path = Column(Text, nullable=False)
    storage_generation = Column(Text, nullable=False)
    consent_version = Column(Text, nullable=False)
    granted_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    revoked_at = Column(DateTime(timezone=True))


class AssessmentAccessLog(Base):
    __tablename__ = 'assessment_access_log'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    share_id = Column(PG_UUID(as_uuid=True), ForeignKey('assessment_shares.id', ondelete='CASCADE'), nullable=False)
    viewer_id = Column(Text, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    accessed_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class HiringApplication(Base):
    """One applicant's role application with an immutable question/policy snapshot."""
    __tablename__ = 'hiring_applications'
    __table_args__ = (UniqueConstraint('role_posting_id', 'applicant_id', name='uq_hiring_application_role_applicant'),)
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_posting_id = Column(PG_UUID(as_uuid=True), ForeignKey('role_postings.id', ondelete='CASCADE'), nullable=False)
    applicant_id = Column(Text, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    status = Column(Text, nullable=False, default='assessment_required')
    applicant_details = Column(JSONB)
    assessment_criteria = Column(JSONB)
    screening_result = Column(JSONB)
    screening_outcome = Column(Text)
    question_schema = Column(JSONB, nullable=False, default=list)
    answers = Column(JSONB, nullable=False, default=dict)
    location = Column(JSONB)
    attempt_limit = Column(Integer, nullable=False, default=3)
    consent_version = Column(Text, nullable=False)
    consented_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class HiringAssessmentSession(Base):
    """Reserved attempt slot handed to the unchanged CookCredit Skill capture site."""
    __tablename__ = 'hiring_assessment_sessions'
    __table_args__ = (
        UniqueConstraint('application_id', 'slot', name='uq_hiring_assessment_slot'),
        UniqueConstraint('engine_assessment_id', name='uq_hiring_engine_assessment'),
    )
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(PG_UUID(as_uuid=True), ForeignKey('hiring_applications.id', ondelete='CASCADE'), nullable=False)
    applicant_id = Column(Text, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    slot = Column(Integer, nullable=False)
    status = Column(Text, nullable=False, default='started')
    engine_assessment_id = Column(Text)
    attempt_id = Column(PG_UUID(as_uuid=True), ForeignKey('skill_attempts.id', ondelete='SET NULL'))
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))


class HiringApplicationEvent(Base):
    __tablename__ = 'hiring_application_events'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(PG_UUID(as_uuid=True), ForeignKey('hiring_applications.id', ondelete='CASCADE'), nullable=False)
    actor_id = Column(Text, ForeignKey('users.id', ondelete='SET NULL'))
    event_type = Column(Text, nullable=False)
    detail = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class PartnerApiKey(Base):
    __tablename__ = 'partner_api_keys'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey('orgs.id', ondelete='CASCADE'), nullable=False)
    name = Column(Text, nullable=False)
    key_prefix = Column(Text, nullable=False, unique=True)
    secret_hash = Column(Text, nullable=False, unique=True)
    scopes = Column(ARRAY(Text), nullable=False, default=list)
    environment = Column(Text, nullable=False, default='live')
    created_by = Column(Text, ForeignKey('users.id', ondelete='SET NULL'))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_used_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))

    __table_args__ = (Index('idx_partner_api_keys_org', 'org_id', 'created_at'),)


class PartnerInvitation(Base):
    __tablename__ = 'partner_invitations'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey('orgs.id', ondelete='CASCADE'), nullable=False)
    role_posting_id = Column(PG_UUID(as_uuid=True), ForeignKey('role_postings.id', ondelete='CASCADE'), nullable=False)
    token_hash = Column(Text, nullable=False, unique=True)
    token_ciphertext = Column(Text, nullable=False)
    candidate_email = Column(Text, nullable=False)
    external_candidate_id = Column(Text)
    external_job_id = Column(Text)
    job_title = Column(Text)
    assessment_profile = Column(Text, nullable=False, default='guillotine_dice')
    assessment_profile_version = Column(Text, nullable=False, default='knife-dice-v1')
    attempt_limit = Column(Integer, nullable=False, default=3)
    return_url = Column(Text)
    environment = Column(Text, nullable=False, default='live')
    idempotency_key = Column(Text, nullable=False)
    request_fingerprint = Column(Text)
    request_config = Column(JSONB)
    application_id = Column(PG_UUID(as_uuid=True), ForeignKey('hiring_applications.id', ondelete='SET NULL'))
    status = Column(Text, nullable=False, default='pending')
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    accepted_at = Column(DateTime(timezone=True))
    canceled_at = Column(DateTime(timezone=True))
    review_decision = Column(Text)
    review_reason = Column(Text)
    reviewed_by = Column(Text, ForeignKey('users.id', ondelete='SET NULL'))
    reviewed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint('org_id', 'environment', 'idempotency_key', name='uq_partner_invitation_environment_idempotency'),
        Index('idx_partner_invitations_org_created', 'org_id', 'created_at'),
    )


class PartnerWebhook(Base):
    __tablename__ = 'partner_webhooks'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(PG_UUID(as_uuid=True), ForeignKey('orgs.id', ondelete='CASCADE'), nullable=False)
    url = Column(Text, nullable=False)
    environment = Column(Text, nullable=False, default='live')
    event_types = Column(ARRAY(Text), nullable=False, default=list)
    secret_ciphertext = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    failure_count = Column(Integer, nullable=False, default=0)
    disabled_at = Column(DateTime(timezone=True))
    created_by = Column(Text, ForeignKey('users.id', ondelete='SET NULL'))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (UniqueConstraint('org_id', 'environment', 'url', name='uq_partner_webhook_environment_url'),)


class PartnerWebhookDelivery(Base):
    __tablename__ = 'partner_webhook_deliveries'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = Column(PG_UUID(as_uuid=True), ForeignKey('partner_webhooks.id', ondelete='CASCADE'), nullable=False)
    event_id = Column(PG_UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    event_type = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False, default='pending')
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    lock_token = Column(PG_UUID(as_uuid=True))
    locked_until = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint('webhook_id', 'event_id', name='uq_partner_webhook_delivery_event'),
        Index('idx_partner_webhook_delivery_due', 'status', 'next_attempt_at'),
    )
