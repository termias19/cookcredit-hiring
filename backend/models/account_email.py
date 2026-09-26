"""Durable account email outbox. Action codes are generated at delivery, never stored."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from services.database import Base


class AccountEmail(Base):
    __tablename__ = 'account_emails'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedupe_key = Column(Text, nullable=False, unique=True)
    kind = Column(Text, nullable=False)
    recipient = Column(Text, nullable=False)
    user_id = Column(Text)
    status = Column(Text, nullable=False, default='pending')
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    lease_until = Column(DateTime(timezone=True))
    lease_token = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    access_request_id = Column(UUID(as_uuid=True))
    access_revision = Column(Integer)
