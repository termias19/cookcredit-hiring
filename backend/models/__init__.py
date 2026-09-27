"""
CookCredit SQLAlchemy models.

These map 1:1 to the tables in migrations/001_initial.sql.
PostGIS columns use GeoAlchemy2 Geography type.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Text, Integer, Numeric, Boolean, Date, Time,
    DateTime, ForeignKey, CheckConstraint, UniqueConstraint,
    ARRAY, Index, func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography

from services.database import Base

import uuid


def _utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Text, primary_key=True)  # Firebase UID
    email = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    phone = Column(Text)
    roles = Column(ARRAY(Text), default=["eater"])
    active_role = Column(Text, default="eater")
    photo_url = Column(Text)
    fcm_token = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    eater_profile = relationship("EaterProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    cook_profile = relationship("CookProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    dishes = relationship("Dish", back_populates="cook", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "phone": self.phone,
            "roles": self.roles or [],
            "activeRole": self.active_role,
            "photoUrl": self.photo_url,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class EaterProfile(Base):
    __tablename__ = "eater_profiles"

    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    address_street = Column(Text)
    address_city = Column(Text)
    address_state = Column(Text)
    address_zip = Column(Text)
    location = Column(Geography("POINT", srid=4326))
    dietary_preferences = Column(ARRAY(Text))
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="eater_profile")

    def to_dict(self):
        return {
            "userId": self.user_id,
            "addressStreet": self.address_street,
            "addressCity": self.address_city,
            "addressState": self.address_state,
            "addressZip": self.address_zip,
            "dietaryPreferences": self.dietary_preferences or [],
        }


class CookProfile(Base):
    __tablename__ = "cook_profiles"

    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    bio = Column(Text)
    specialties = Column(ARRAY(Text))
    cuisines = Column(ARRAY(Text))
    price_per_hour = Column(Numeric(6, 2))
    travel_radius_miles = Column(Numeric(4, 1))
    base_location = Column(Geography("POINT", srid=4326))
    base_city = Column(Text)
    base_state = Column(Text)
    portfolio_photos = Column(ARRAY(Text))
    stripe_account_id = Column(Text)
    stripe_onboarded = Column(Boolean, default=False)
    skill_score = Column(Numeric(5, 2))   # 0..100.00 (4,2 overflowed on a perfect 100)
    skill_verified = Column(Boolean, default=False)
    # Chopping skill-test gate (filled by /api/skills/submit).
    skill_tier = Column(Text)                      # gold|silver|bronze|None
    skill_test_at = Column(DateTime(timezone=True))
    skill_test_video_url = Column(Text)            # Firebase Storage URL (optional)
    skill_test_result = Column(JSONB)              # full scoring breakdown
    years_experience = Column(Integer)
    dietary_capabilities = Column(ARRAY(Text))
    applied_at = Column(DateTime(timezone=True))   # set when the cook submits their application
    approved = Column(Boolean, default=False)       # flipped by an admin after review
    rejected_at = Column(DateTime(timezone=True))   # set when an admin rejects the application
    review_note = Column(Text)                       # optional admin note (esp. on rejection)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="cook_profile")

    def to_dict(self):
        return {
            "userId": self.user_id,
            "bio": self.bio,
            "specialties": self.specialties or [],
            "cuisines": self.cuisines or [],
            "pricePerHour": float(self.price_per_hour) if self.price_per_hour else None,
            "travelRadiusMiles": float(self.travel_radius_miles) if self.travel_radius_miles else None,
            "baseCity": self.base_city,
            "baseState": self.base_state,
            "portfolioPhotos": self.portfolio_photos or [],
            "stripeOnboarded": self.stripe_onboarded,
            "skillScore": float(self.skill_score) if self.skill_score else None,
            "skillVerified": self.skill_verified,
            "skillTier": self.skill_tier,
            "skillTestAt": self.skill_test_at.isoformat() if self.skill_test_at else None,
            # NB: the biometric skillTestVideoUrl is deliberately NOT serialized here. It is served
            # only via the gated /api/business/candidate/<id>/video path (business role + org-pipeline
            # scope), so a future endpoint returning a foreign cook's profile can't leak the clip.
            "skillTestResult": self.skill_test_result,
            "yearsExperience": self.years_experience,
            "dietaryCapabilities": self.dietary_capabilities or [],
            "appliedAt": self.applied_at.isoformat() if self.applied_at else None,
            "approved": self.approved,
            "reviewNote": self.review_note,
            # Derived application status for the client: none | pending | approved | rejected
            "applicationStatus": (
                "approved" if self.approved
                else "rejected" if self.rejected_at
                else "pending" if self.applied_at
                else "none"),
        }


class Dish(Base):
    __tablename__ = "dishes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text)
    photo_url = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    cook = relationship("User", back_populates="dishes")

    def to_dict(self):
        return {
            "id": str(self.id),
            "cookId": self.cook_id,
            "name": self.name,
            "description": self.description,
            "photoUrl": self.photo_url,
            "sortOrder": self.sort_order,
        }


class CookAvailability(Base):
    __tablename__ = "cook_availability"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day_of_week = Column(Integer, nullable=False)
    start_hour = Column(Integer, nullable=False)
    end_hour = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("cook_id", "day_of_week", "start_hour"),
        CheckConstraint("day_of_week BETWEEN 0 AND 6"),
        CheckConstraint("start_hour BETWEEN 0 AND 23"),
        CheckConstraint("end_hour BETWEEN 0 AND 23"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "dayOfWeek": self.day_of_week,
            "startHour": self.start_hour,
            "endHour": self.end_hour,
        }


class CookBlockedDate(Base):
    __tablename__ = "cook_blocked_dates"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    blocked_date = Column(Date, nullable=False)
    reason = Column(Text)

    __table_args__ = (
        UniqueConstraint("cook_id", "blocked_date"),
    )


class PantryItem(Base):
    __tablename__ = "pantry_items"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    category = Column(Text)
    item_type = Column(Text, default="staple")
    added_at = Column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "category": self.category,
            "itemType": self.item_type,
        }


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eater_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, default="requested")
    scheduled_date = Column(Date, nullable=False)
    scheduled_start_time = Column(Time, nullable=False)
    estimated_duration = Column(Numeric(3, 1), nullable=False)
    eater_address = Column(Text)
    eater_location = Column(Geography("POINT", srid=4326))
    price_per_hour = Column(Numeric(6, 2), nullable=False)
    estimated_total = Column(Numeric(8, 2), nullable=False)
    actual_duration = Column(Numeric(3, 1))
    final_total = Column(Numeric(8, 2))
    platform_fee = Column(Numeric(8, 2))
    cook_payout = Column(Numeric(8, 2))
    stripe_payment_intent_id = Column(Text)
    eater_notes = Column(Text)
    cook_notes = Column(Text)
    cancellation_reason = Column(Text)
    cancelled_by = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    eater = relationship("User", foreign_keys=[eater_id])
    cook = relationship("User", foreign_keys=[cook_id])
    ingredient_requests = relationship("IngredientRequest", back_populates="booking", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="booking")

    __table_args__ = (
        CheckConstraint(
            "status IN ('requested','accepted','ingredient_request','confirmed',"
            "'in_progress','pending_confirmation','completed','cancelled','disputed')"
        ),
        CheckConstraint("cancelled_by IN ('eater','cook','system')"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "eaterId": self.eater_id,
            "cookId": self.cook_id,
            "status": self.status,
            "scheduledDate": self.scheduled_date.isoformat() if self.scheduled_date else None,
            "scheduledStartTime": self.scheduled_start_time.isoformat() if self.scheduled_start_time else None,
            "estimatedDuration": float(self.estimated_duration) if self.estimated_duration else None,
            "eaterAddress": self.eater_address,
            "pricePerHour": float(self.price_per_hour) if self.price_per_hour else None,
            "estimatedTotal": float(self.estimated_total) if self.estimated_total else None,
            "actualDuration": float(self.actual_duration) if self.actual_duration else None,
            "finalTotal": float(self.final_total) if self.final_total else None,
            "platformFee": float(self.platform_fee) if self.platform_fee else None,
            "cookPayout": float(self.cook_payout) if self.cook_payout else None,
            "eaterNotes": self.eater_notes,
            "cookNotes": self.cook_notes,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class IngredientRequest(Base):
    __tablename__ = "ingredient_requests"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(PG_UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    item = Column(Text, nullable=False)
    note = Column(Text)

    booking = relationship("Booking", back_populates="ingredient_requests")

    def to_dict(self):
        return {"id": str(self.id), "item": self.item, "note": self.note}


class Review(Base):
    __tablename__ = "reviews"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(PG_UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewee_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False)
    rating = Column(Integer, nullable=False)
    text = Column(Text)
    tags = Column(ARRAY(Text))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    booking = relationship("Booking", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("booking_id", "reviewer_id"),
        CheckConstraint("role IN ('eater_reviewing_cook','cook_reviewing_eater')"),
        CheckConstraint("rating BETWEEN 1 AND 5"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "bookingId": str(self.booking_id),
            "reviewerId": self.reviewer_id,
            "revieweeId": self.reviewee_id,
            "role": self.role,
            "rating": self.rating,
            "text": self.text,
            "tags": self.tags or [],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class Message(Base):
    """Booking-scoped messages between eater and cook."""
    __tablename__ = "messages"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(PG_UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "bookingId": str(self.booking_id),
            "senderId": self.sender_id,
            "text": self.text,
            "read": self.read,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class Assessment(Base):
    """A standalone knife-skill assessment — the graded-assessment product.

    Decoupled from the cook application (CookProfile.skill_*): ANY user can be
    graded and keep a history. This table is the product's system of record and
    the demonstration-data flywheel. The cook gate may later reference a user's
    best/most-recent assessment, but it is not coupled here.

    kind: 'technique' (Launch 1, hand-landmark oscillation grade) | 'fused'
    (Launch 2, + the engine video-CV piece-size half).
    """
    __tablename__ = "assessments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(Text, nullable=False, default="technique")
    skill_score = Column(Numeric(5, 2))      # 0..100.00; None when unscorable
    verified = Column(Boolean, nullable=False, default=False)
    tier = Column(Text)                       # gold | silver | bronze | None
    result = Column(JSONB)                    # full scoring breakdown + capture metadata
    video_url = Column(Text)                  # optional recorded clip (Firebase Storage)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user = relationship("User")

    __table_args__ = (
        Index("idx_assessments_user_created", "user_id", "created_at"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "kind": self.kind,
            "skillScore": float(self.skill_score) if self.skill_score is not None else None,
            "verified": self.verified,
            "tier": self.tier,
            "videoUrl": self.video_url,
            "result": self.result,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


# ── Dual skill-scoring path (the append-only attempt + transition log) ──────────
# The on-device (provisional, client-claimed) score is recorded immediately; the
# uploaded VIDEO is then re-derived by the GPU scorer and reconciled against it. A
# credential is eligible ONLY on VERIFIED. See migrations/006_skill_attempts.sql.

# Forward-only state machine. Terminal states are final — a retest is a NEW attempt
# (new session_id), never a re-open, so the history stays append-only and auditable.
ATTEMPT_STATES = ("PROVISIONAL", "VERIFYING", "VERIFIED", "DISPUTED", "INSUFFICIENT")
ATTEMPT_TERMINAL = ("VERIFIED", "DISPUTED", "INSUFFICIENT")
_ALLOWED_TRANSITIONS = {
    # PROVISIONAL can fail straight to a terminal state if there is no scorable video.
    "PROVISIONAL": {"VERIFYING", "VERIFIED", "DISPUTED", "INSUFFICIENT"},
    # VERIFYING -> VERIFYING is allowed for an idempotent recompute retry on a transient error.
    "VERIFYING": {"VERIFYING", "VERIFIED", "DISPUTED", "INSUFFICIENT"},
    "VERIFIED": set(),
    "DISPUTED": set(),
    "INSUFFICIENT": set(),
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    """True iff `from_state` -> `to_state` is a legal forward move in the attempt
    state machine. Used to guard the append-only transition writes."""
    if to_state not in ATTEMPT_STATES:
        return False
    return to_state in _ALLOWED_TRANSITIONS.get(from_state, set())


class SkillAttempt(Base):
    """One knife-skill attempt: the provisional on-device score plus, after the
    uploaded video is re-derived by the GPU scorer, the authoritative server block
    and the reconciliation between them. Idempotent on (user_id, session_id)."""
    __tablename__ = "skill_attempts"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(Text, nullable=False)               # client-generated UUID (idempotency key)
    profile_id = Column(Text, nullable=False, default="guillotine_dice")
    verification_state = Column(Text, nullable=False, default="PROVISIONAL")
    on_device_score = Column(Numeric(5, 2))                 # client-claimed provisional
    on_device_block = Column(JSONB)                         # client breakdown
    local_score = Column(Numeric(5, 2))                     # server recompute from trajectory (still forgeable)
    local_block = Column(JSONB)                             # score_trajectory() output
    server_block = Column(JSONB)                            # GPU /score response
    reconciliation = Column(JSONB)                          # {agreement, tamper_flag, motion_match, product_score, reason}
    authoritative_score = Column(Numeric(5, 2))             # video-derived skill number when VERIFIED
    tier = Column(Text)
    trajectory = Column(JSONB)                              # kept for re-derivation/audit
    metadata_ = Column("metadata", JSONB)                  # capture metadata (column name 'metadata')
    video_url = Column(Text)
    error = Column(Text)
    recompute_count = Column(Integer, nullable=False, default=0)
    recompute_lease_id = Column(PG_UUID(as_uuid=True))
    recompute_lease_until = Column(DateTime(timezone=True))
    # Durable dispatch intent, committed atomically with the assessment.
    dispatch_due_at = Column(DateTime(timezone=True))
    dispatch_token = Column(PG_UUID(as_uuid=True))
    dispatch_failures = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User")
    events = relationship("SkillAttemptEvent", back_populates="attempt",
                          cascade="all, delete-orphan", order_by="SkillAttemptEvent.created_at")

    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_skill_attempts_session"),
        Index("idx_skill_attempts_user_created", "user_id", "created_at"),
        Index("idx_skill_attempts_state", "verification_state"),
    )

    def to_dict(self, include_trajectory: bool = False) -> dict:
        """Owner-facing view: BOTH scores + the verification state. The raw video
        URL is deliberately NOT serialized (biometric — served only via the gated
        business path); `hasVideo` tells the client a clip exists."""
        out = {
            "id": str(self.id),
            "sessionId": self.session_id,
            "profileId": self.profile_id,
            "verificationState": self.verification_state,
            "onDevice": {
                "score": float(self.on_device_score) if self.on_device_score is not None else None,
                **(self.on_device_block or {}),
            },
            "local": {
                "score": float(self.local_score) if self.local_score is not None else None,
                **(self.local_block or {}),
            },
            "server": self.server_block,
            "reconciliation": self.reconciliation,
            "authoritativeScore": float(self.authoritative_score) if self.authoritative_score is not None else None,
            "tier": self.tier,
            "credentialEligible": self.verification_state == "VERIFIED",
            "metadata": self.metadata_,
            "hasVideo": bool(self.video_url),
            "error": self.error,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_trajectory:
            out["trajectory"] = self.trajectory
        return out


class SkillAttemptEvent(Base):
    """Append-only record of one state transition on a SkillAttempt (never mutated
    or deleted). The attempt's verification_state is the materialized current value;
    this table is the source of truth for how it got there."""
    __tablename__ = "skill_attempt_events"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(PG_UUID(as_uuid=True), ForeignKey("skill_attempts.id", ondelete="CASCADE"), nullable=False)
    from_state = Column(Text)                               # NULL for the initial PROVISIONAL creation
    to_state = Column(Text, nullable=False)
    detail = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    attempt = relationship("SkillAttempt", back_populates="events")

    __table_args__ = (
        Index("idx_skill_attempt_events_attempt", "attempt_id", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "attemptId": str(self.attempt_id),
            "fromState": self.from_state,
            "toState": self.to_state,
            "detail": self.detail,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class Beam(Base):
    """An eater's broadcast craving. Fans out to many cooks (one BeamResponse recipient
    row per matched cook); each cook may respond with a note + price; the eater reviews
    responders and picks ONE -> status 'fulfilled'. PAYMENT-AGNOSTIC: no settlement here,
    so the same model serves both US (Stripe) and ET/Addis (Chapa + cash) markets.

    Matching is city-wide first (lower(city) against cook_profiles.base_city). eater_location
    is reserved for a later GPS 'nearby' radius (ST_DWithin); no geocoding is done yet."""
    __tablename__ = "beams"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eater_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    craving_text = Column(Text, nullable=False)
    photo_url = Column(Text)
    scope = Column(Text, nullable=False, default="citywide")
    city = Column(Text)
    state = Column(Text)
    eater_location = Column(Geography("POINT", srid=4326))
    status = Column(Text, nullable=False, default="open")
    chosen_cook_id = Column(Text, ForeignKey("users.id", ondelete="SET NULL"))
    # Circular FK to the picked response; use_alter mirrors the post-create ALTER in the migration.
    chosen_response_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("beam_responses.id", use_alter=True,
                   name="fk_beams_chosen_response", ondelete="SET NULL"),
    )
    matched_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    eater = relationship("User", foreign_keys=[eater_id])
    responses = relationship(
        "BeamResponse",
        backref="beam",
        cascade="all, delete-orphan",
        foreign_keys="BeamResponse.beam_id",
    )

    __table_args__ = (
        CheckConstraint("scope IN ('nearby','citywide')"),
        CheckConstraint("status IN ('open','fulfilled','expired','cancelled')"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "eaterId": self.eater_id,
            "cravingText": self.craving_text,
            "photoUrl": self.photo_url,
            "scope": self.scope,
            "city": self.city,
            "state": self.state,
            "status": self.status,
            "chosenCookId": self.chosen_cook_id,
            "chosenResponseId": str(self.chosen_response_id) if self.chosen_response_id else None,
            "matchedCount": self.matched_count,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class BeamResponse(Base):
    """One matched cook's recipient/seen row for a beam, which also carries that cook's
    response. 'pending' = matched but not yet acted on (the cook's inbox item);
    'responded' = the cook offered (note + price); 'declined' = cook dismissed it;
    'chosen'/'not_chosen' are set when the eater picks a responder."""
    __tablename__ = "beam_responses"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    beam_id = Column(PG_UUID(as_uuid=True), ForeignKey("beams.id", ondelete="CASCADE"), nullable=False)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    note = Column(Text)
    price = Column(Numeric(8, 2))
    seen_at = Column(DateTime(timezone=True))
    responded_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    cook = relationship("User", foreign_keys=[cook_id])

    __table_args__ = (
        UniqueConstraint("beam_id", "cook_id", name="uq_beam_responses_beam_cook"),
        CheckConstraint("status IN ('pending','responded','declined','chosen','not_chosen')"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "beamId": str(self.beam_id),
            "cookId": self.cook_id,
            "status": self.status,
            "note": self.note,
            "price": float(self.price) if self.price is not None else None,
            "seenAt": self.seen_at.isoformat() if self.seen_at else None,
            "respondedAt": self.responded_at.isoformat() if self.responded_at else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class Order(Base):
    """An eater's order for a chosen beam response — the settlement record the payment-agnostic
    beam flow deliberately does NOT create at /choose. One order per chosen BeamResponse.

    ET pays via Chapa (telebirr / Chapa / CBE Birr all settle through Chapa) or cash-on-delivery;
    the same row also serves the US market (cash today). `amount` snapshots the cook's quoted price
    at choose time (BeamResponse.price, which may be null). `payment_status` lifecycle:
      cod   -> 'cod_pending' (eater pays cash on delivery; no online settlement)
      online-> 'pending' -> 'awaiting_payment' (Chapa checkout issued) -> 'paid' | 'failed'."""
    __tablename__ = "orders"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    beam_id = Column(PG_UUID(as_uuid=True), ForeignKey("beams.id", ondelete="CASCADE"), nullable=False)
    beam_response_id = Column(PG_UUID(as_uuid=True), ForeignKey("beam_responses.id", ondelete="CASCADE"), nullable=False)
    eater_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    cook_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(8, 2))                       # snapshot of the cook's quote; may be null
    currency = Column(Text, nullable=False, default="USD")  # set per market at insert (ETB for ET)
    payment_method = Column(Text, nullable=False)        # cod | chapa | telebirr | cbe
    payment_status = Column(Text, nullable=False, default="pending")
    chapa_tx_ref = Column(Text)                          # Chapa transaction reference (online ET)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    eater = relationship("User", foreign_keys=[eater_id])
    cook = relationship("User", foreign_keys=[cook_id])

    __table_args__ = (
        UniqueConstraint("beam_response_id", name="uq_orders_beam_response"),
        CheckConstraint("payment_method IN ('cod','chapa','telebirr','cbe')"),
        CheckConstraint(
            "payment_status IN ('pending','awaiting_payment','paid','cod_pending','failed','cancelled','refunded')"
        ),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "beamId": str(self.beam_id),
            "beamResponseId": str(self.beam_response_id),
            "eaterId": self.eater_id,
            "cookId": self.cook_id,
            "amount": float(self.amount) if self.amount is not None else None,
            "currency": self.currency,
            "paymentMethod": self.payment_method,
            "paymentStatus": self.payment_status,
            "chapaTxRef": self.chapa_tx_ref,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── B2B hiring models (org workspace, roles, pipeline, shortlists, resume, AEDT audit) ──
# Imported so the classes register with Base.metadata and are importable from `models`.
from models.business import (  # noqa: E402,F401
    Org, OrgAssessmentUsage, OrgMembership, OrgInvitation, RolePosting, PipelineCard, StripeEvent,
    Shortlist, ShortlistMember, ResumeKeypoints, AedtAuditLog,
    CandidateNotice, OptOutRequest, AssessmentShare, AssessmentAccessLog,
    HiringApplication, HiringAssessmentSession, HiringApplicationEvent,
    PartnerApiKey, PartnerInvitation, PartnerWebhook, PartnerWebhookDelivery,
)

# ── Ethio-Cook (Addis) marketplace models — kitchens, menus, food orders ──
from models.ethio import (  # noqa: E402,F401
    Kitchen, MenuItem, EthioOrder, EthioOrderItem,
)
from models.account_email import AccountEmail  # noqa: E402,F401
from models.hiring_access import HiringAccessRequest, HiringAccessEvent, HiringAccessInbox  # noqa: E402,F401

from models.billing_catalog import HiringPrice  # noqa: E402,F401
