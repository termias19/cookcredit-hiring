"""Home-only extensions to existing User, CookProfile and Booking records.

Do not import these from the Hiring application or its migration runner.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, Boolean, DateTime, ForeignKey
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
