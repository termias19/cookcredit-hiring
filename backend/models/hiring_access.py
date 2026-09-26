import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from services.database import Base


def now():
    return datetime.now(timezone.utc)


class HiringAccessRequest(Base):
    __tablename__ = 'hiring_access_requests'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False, unique=True)
    name = Column(Text, nullable=False, default='')
    company = Column(Text, nullable=False, default='')
    message = Column(Text, nullable=False, default='')
    source = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default='pending')
    revision = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    decided_by = Column(Text)
    decided_at = Column(DateTime(timezone=True))

    def to_dict(self):
        return dict(id=str(self.id), email=self.email, name=self.name, company=self.company,
                    message=self.message, source=self.source, status=self.status, revision=self.revision,
                    createdAt=self.created_at.isoformat(), updatedAt=self.updated_at.isoformat(),
                    decidedAt=self.decided_at.isoformat() if self.decided_at else None)


class HiringAccessEvent(Base):
    __tablename__ = 'hiring_access_events'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey('hiring_access_requests.id'), nullable=False)
    actor_id = Column(Text)
    action = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class HiringAccessInbox(Base):
    __tablename__ = 'hiring_access_inbox'
    id = Column(Text, primary_key=True)
    uid_validity = Column(Text)
    last_uid = Column(BigInteger, nullable=False, default=0)
    checked_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
