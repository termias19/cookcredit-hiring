"""Home-only drafts using the established campaign column definitions.

The table definitions are copied from the existing SQLAlchemy models, not from
the Hiring database. No recipients or subscriptions are imported or created.
"""
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from services.database import Base
from models.customer_mail import Campaign


class HomeCampaign(Base):
    __table__ = Campaign.__table__.to_metadata(Base.metadata, name='home_campaigns')
    __table__.append_column(Column('design', JSONB, nullable=False, default=dict))

    def to_dict(self):
        return {**Campaign.to_dict(self), 'design': self.design or {}}
