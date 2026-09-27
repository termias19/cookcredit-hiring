"""Opt-in offers and campaign state; delivery uses the account email outbox."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Boolean, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from services.database import Base


def now():
    return datetime.now(timezone.utc)


class EmailPreference(Base):
    __tablename__ = 'hiring_email_preferences'
    user_id = Column(Text, primary_key=True)
    email = Column(Text, nullable=False)
    opted_in = Column(Boolean, nullable=False, default=False)
    consent_version = Column(Text, nullable=False, default='hiring-offers-v1')
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    unsubscribe_token = Column(Text, nullable=False, unique=True)


class Campaign(Base):
    __tablename__ = 'hiring_campaigns'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    postal_address = Column(Text, nullable=False, default='')
    status = Column(Text, nullable=False, default='draft')
    interval_days = Column(Integer, nullable=False, default=0)
    next_run_at = Column(DateTime(timezone=True))
    run_at = Column(DateTime(timezone=True))
    cursor = Column(Text)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)

    def to_dict(self):
        return dict(id=str(self.id), subject=self.subject, body=self.body,
                    postalAddress=self.postal_address, status=self.status,
                    intervalDays=self.interval_days, revision=self.revision,
                    nextRunAt=self.next_run_at.isoformat() if self.next_run_at else None)


class CampaignEvent(Base):
    __tablename__ = 'hiring_campaign_events'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), nullable=False)
    actor_id = Column(Text, nullable=False)
    action = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
