"""Versioned hiring prices; historical Stripe prices retain their entitlements."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from services.database import Base

class HiringPrice(Base):
    __tablename__ = 'hiring_prices'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan = Column(Text, nullable=False)
    interval = Column(Text, nullable=False)
    currency = Column(Text, nullable=False, default='usd')
    amount = Column(Integer, nullable=False)
    limits = Column(JSONB, nullable=False)
    state = Column(Text, nullable=False, default='draft')
    active = Column(Boolean, nullable=False, default=False)
    stripe_price_id = Column(Text, unique=True)
    previous_id = Column(UUID(as_uuid=True))
    created_by = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {'id': str(self.id), 'plan': self.plan, 'interval': self.interval,
                'currency': self.currency, 'amount': self.amount, 'limits': self.limits,
                'state': self.state, 'active': self.active,
                'createdAt': self.created_at.isoformat() if self.created_at else None}
