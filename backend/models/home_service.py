"""Home-only extensions to existing User, CookProfile and Booking records.

Do not import these from the Hiring application or its migration runner.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, Boolean, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from services.database import Base


def now():
    return datetime.now(timezone.utc)


class HomeVisit(Base):
    __tablename__ = 'home_visits'
    booking_id = Column(UUID(as_uuid=True), ForeignKey('bookings.id'), primary_key=True)
    service = Column(Text, nullable=False)
    time_zone = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=0)
    instructions = Column(JSONB, nullable=False)
    consent_version = Column(Text, nullable=False)
    consented_at = Column(DateTime(timezone=True), nullable=False, default=now)
    reviewed_at = Column(DateTime(timezone=True))
    reviewed_by = Column(Text, ForeignKey('users.id'))
    helper_accepted_at = Column(DateTime(timezone=True))
    issue_open = Column(Boolean, nullable=False, default=False)
    quote_id = Column(UUID(as_uuid=True))
    customer_confirmed_at = Column(DateTime(timezone=True))
    service_minutes = Column(JSONB)
    recipient = Column(JSONB)
    __table_args__ = (ForeignKeyConstraint(['booking_id', 'quote_id'], ['home_quotes.booking_id', 'home_quotes.id'],
        name='home_visit_current_quote_fk', use_alter=True),)


class HomeHelperPermission(Base):
    __tablename__ = 'home_helper_permissions'
    user_id = Column(Text, ForeignKey('users.id'), primary_key=True)
    enabled = Column(Boolean, nullable=False)
    cooking = Column(Boolean, nullable=False)
    cleaning = Column(Boolean, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeEvent(Base):
    __tablename__ = 'home_events'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), ForeignKey('bookings.id'))
    actor_id = Column(Text, ForeignKey('users.id'), nullable=False)
    action = Column(Text, nullable=False)
    version = Column(Integer)
    # Fixed, non-sensitive fields only; never request bodies or household notes.
    details = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeCommand(Base):
    __tablename__ = 'home_commands'
    actor_id = Column(Text, ForeignKey('users.id'), primary_key=True)
    key_hash = Column(Text, primary_key=True)
    request_hash = Column(Text, nullable=False)
    result = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeRateCard(Base):
    """Append-only pricing versions; activation changes a separate singleton."""
    __tablename__ = 'home_rate_cards'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    previous_id = Column(UUID(as_uuid=True), ForeignKey('home_rate_cards.id'))
    settings = Column(JSONB, nullable=False)
    created_by = Column(Text, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomePricingHead(Base):
    __tablename__ = 'home_pricing_head'
    id = Column(Integer, primary_key=True)
    rate_card_id = Column(UUID(as_uuid=True), ForeignKey('home_rate_cards.id'))


class HomeQuote(Base):
    """Immutable offer. Approval is a separate append-only record."""
    __tablename__ = 'home_quotes'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), ForeignKey('home_visits.booking_id'), nullable=False)
    rate_card_id = Column(UUID(as_uuid=True), ForeignKey('home_rate_cards.id'), nullable=False)
    helper_id = Column(Text, ForeignKey('users.id'), nullable=False)
    issued_version = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)
    digest = Column(Text, nullable=False)
    created_by = Column(Text, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (UniqueConstraint('booking_id', 'id'), UniqueConstraint('booking_id', 'issued_version'))


class HomeQuoteHelperAcceptance(Base):
    __tablename__ = 'home_quote_helper_acceptances'
    quote_id = Column(UUID(as_uuid=True), ForeignKey('home_quotes.id'), primary_key=True)
    helper_id = Column(Text, ForeignKey('users.id'), nullable=False)
    digest = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (UniqueConstraint('quote_id', 'helper_id'),)


class HomeQuoteApproval(Base):
    __tablename__ = 'home_quote_approvals'
    quote_id = Column(UUID(as_uuid=True), ForeignKey('home_quote_helper_acceptances.quote_id'), primary_key=True)
    customer_id = Column(Text, ForeignKey('users.id'), nullable=False)
    digest = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (UniqueConstraint('quote_id', 'customer_id'),)


class HomeMaterialReconciliation(Base):
    """Manual receipt-review accounting; never a transfer or refund instruction."""
    __tablename__ = 'home_material_reconciliations'
    quote_id = Column(UUID(as_uuid=True), ForeignKey('home_quote_approvals.quote_id'), primary_key=True)
    booking_id = Column(UUID(as_uuid=True), ForeignKey('home_visits.booking_id'), nullable=False)
    reviewed_by = Column(Text, ForeignKey('users.id'), nullable=False)
    snapshot = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (ForeignKeyConstraint(['booking_id', 'quote_id'], ['home_quotes.booking_id', 'home_quotes.id'],
        name='home_reconciliation_booking_quote_fk'),)


class HomePayment(Base):
    __tablename__ = 'home_payments'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), ForeignKey('home_visits.booking_id'), nullable=False)
    quote_id = Column(UUID(as_uuid=True), ForeignKey('home_quote_approvals.quote_id'), nullable=False, unique=True)
    customer_id = Column(Text, ForeignKey('users.id'), nullable=False)
    helper_id = Column(Text, ForeignKey('users.id'), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    refunded_cents = Column(Integer, nullable=False, default=0)
    status = Column(Text, nullable=False, default='creating')
    livemode = Column(Boolean, nullable=False)
    checkout_attempt = Column(Integer, nullable=False, default=1)
    checkout_id = Column(Text, unique=True)
    checkout_url = Column(Text)
    payment_intent_id = Column(Text, unique=True)
    charge_id = Column(Text)
    paid_at = Column(DateTime(timezone=True))
    disputed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        ForeignKeyConstraint(['booking_id','quote_id'],['home_quotes.booking_id','home_quotes.id']),
        ForeignKeyConstraint(['quote_id','customer_id'],['home_quote_approvals.quote_id','home_quote_approvals.customer_id']),
        ForeignKeyConstraint(['quote_id','helper_id'],['home_quote_helper_acceptances.quote_id','home_quote_helper_acceptances.helper_id']),
    )


class HomeFinancialOperation(Base):
    __tablename__ = 'home_financial_operations'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id = Column(UUID(as_uuid=True), ForeignKey('home_visits.booking_id'))
    payment_id = Column(UUID(as_uuid=True), ForeignKey('home_payments.id'))
    actor_id = Column(Text, ForeignKey('users.id'), nullable=False)
    kind = Column(Text, nullable=False)
    dedupe_key = Column(Text, nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    status = Column(Text, nullable=False, default='pending')
    provider_id = Column(Text)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, default=now)
    first_started_at = Column(DateTime(timezone=True))
    mutation_started_at = Column(DateTime(timezone=True))
    lease_until = Column(DateTime(timezone=True))
    lease_token = Column(UUID(as_uuid=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeStripeEvent(Base):
    __tablename__ = 'home_stripe_events'
    id = Column(Text, primary_key=True)
    kind = Column(Text, nullable=False)
    object_id = Column(Text, nullable=False)
    payment_id = Column(UUID(as_uuid=True), ForeignKey('home_payments.id'))
    helper_id = Column(Text, ForeignKey('users.id'))
    livemode = Column(Boolean, nullable=False)
    status = Column(Text, nullable=False, default='pending')
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, default=now)
    lease_until = Column(DateTime(timezone=True))
    lease_token = Column(UUID(as_uuid=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeHousehold(Base):
    __tablename__ = 'home_households'
    user_id = Column(Text, ForeignKey('eater_profiles.user_id'), primary_key=True)
    instructions = Column(JSONB, nullable=False)
    consented_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeCallback(Base):
    __tablename__ = 'home_callbacks'
    id = Column(UUID(as_uuid=True), primary_key=True)
    fingerprint = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    phone = Column(Text, nullable=False)
    preferred_time = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default='requested')
    version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeReceipt(Base):
    __tablename__ = 'home_receipts'
    id = Column(UUID(as_uuid=True), primary_key=True)
    booking_id = Column(UUID(as_uuid=True), ForeignKey('home_visits.booking_id'), nullable=False)
    quote_id = Column(UUID(as_uuid=True), ForeignKey('home_quotes.id'), nullable=False)
    uploaded_by = Column(Text, ForeignKey('users.id'), nullable=False)
    request_hash = Column(Text, unique=True, nullable=False)
    original_hash = Column(Text, nullable=False)
    object_path = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default='uploading')
    generation = Column(Text)
    sha256 = Column(Text)
    size_bytes = Column(Integer, nullable=False, default=0)
    content_type = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (ForeignKeyConstraint(['booking_id','quote_id'],['home_quotes.booking_id','home_quotes.id']),)


class HomeNotificationCursor(Base):
    __tablename__ = 'home_notification_cursors'
    event_id = Column(UUID(as_uuid=True), ForeignKey('home_events.id'), primary_key=True)
    status = Column(Text, nullable=False, default='pending')
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HomeAccessAudit(Base):
    __tablename__ = 'home_access_audit'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id = Column(Text, ForeignKey('users.id'), nullable=False)
    action = Column(Text, nullable=False)
    subject_id = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
