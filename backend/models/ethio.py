"""
Ethio-Cook (Addis) marketplace models — kitchens, their menus, and food orders.
Map 1:1 to migrations/010_ethio_marketplace.sql.

This is the ET food-ordering marketplace (order a dish from a verified home kitchen; delivery or
pickup; pay telebirr / Chapa / CBE Birr / cash-on-delivery). It is separate from the beam broadcast
and the US in-home booking flows. Amounts are ETB major units.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Text, Integer, Numeric, Boolean, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
import uuid

from services.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Kitchen(Base):
    """A cook's storefront. `id` is a URL slug (e.g. 'tsehay') used by /et/kitchen/:id. Seeded demo
    kitchens have a null cook_id; a real cook owns the kitchen they create."""
    __tablename__ = "ethio_kitchens"

    id = Column(Text, primary_key=True)                                   # slug
    cook_id = Column(Text, ForeignKey("users.id", ondelete="SET NULL"))   # owner; null for seed demo
    name = Column(Text, nullable=False)
    initial = Column(Text)
    tier = Column(Text, nullable=False, default="bronze")                 # gold | silver | bronze
    score = Column(Integer, nullable=False, default=0)                    # verified skill score 0-100
    rating = Column(Numeric(2, 1))
    hood = Column(Text)
    city = Column(Text, nullable=False, default="Addis Ababa")
    base_price = Column(Numeric(8, 2))
    mode = Column(Text, nullable=False, default="delivery")               # delivery | pickup
    is_open = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    menu = relationship("MenuItem", back_populates="kitchen", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("tier IN ('gold','silver','bronze')"),
        CheckConstraint("mode IN ('delivery','pickup')"),
    )

    def to_dict(self, with_menu=False):
        items = sorted(self.menu, key=lambda m: (m.created_at or _utcnow()))
        d = {
            "id": self.id,
            "cookId": self.cook_id,
            "name": self.name,
            "init": self.initial,
            "tier": self.tier,
            "score": self.score,
            "rating": float(self.rating) if self.rating is not None else None,
            "hood": self.hood,
            "city": self.city,
            "price": float(self.base_price) if self.base_price is not None else None,
            "mode": self.mode,
            "isOpen": self.is_open,
            "dishes": [m.name for m in items],
        }
        if with_menu:
            d["menu"] = [m.to_dict() for m in items]
        return d


class MenuItem(Base):
    __tablename__ = "ethio_menu_items"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kitchen_id = Column(Text, ForeignKey("ethio_kitchens.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    price = Column(Numeric(8, 2), nullable=False)
    available = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    kitchen = relationship("Kitchen", back_populates="menu")

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "price": float(self.price) if self.price is not None else None,
            "avail": self.available,
        }


class EthioOrder(Base):
    __tablename__ = "ethio_orders"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eater_id = Column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kitchen_id = Column(Text, ForeignKey("ethio_kitchens.id", ondelete="CASCADE"), nullable=False)
    mode = Column(Text, nullable=False, default="delivery")               # delivery | pickup
    payment_method = Column(Text, nullable=False)                         # cod | telebirr | chapa | cbe
    payment_status = Column(Text, nullable=False, default="pending")      # pending | cod_pending | paid | failed
    status = Column(Text, nullable=False, default="new")                  # new | preparing | ready | delivered | cancelled
    total = Column(Numeric(8, 2), nullable=False)
    address = Column(Text)                                                # delivery address (nullable for pickup)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    items = relationship("EthioOrderItem", back_populates="order", cascade="all, delete-orphan")
    kitchen = relationship("Kitchen")

    __table_args__ = (
        CheckConstraint("mode IN ('delivery','pickup')"),
        CheckConstraint("payment_method IN ('cod','telebirr','chapa','cbe')"),
        CheckConstraint("payment_status IN ('pending','cod_pending','paid','failed')"),
        CheckConstraint("status IN ('new','preparing','ready','delivered','cancelled')"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "eaterId": self.eater_id,
            "kitchenId": self.kitchen_id,
            "kitchenName": self.kitchen.name if self.kitchen else None,
            "hood": self.kitchen.hood if self.kitchen else None,
            "mode": self.mode,
            "paymentMethod": self.payment_method,
            "paymentStatus": self.payment_status,
            "status": self.status,
            "total": float(self.total) if self.total is not None else None,
            "address": self.address,
            "items": [it.to_dict() for it in self.items],
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class EthioOrderItem(Base):
    __tablename__ = "ethio_order_items"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(PG_UUID(as_uuid=True), ForeignKey("ethio_orders.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)            # dish name snapshot
    price = Column(Numeric(8, 2), nullable=False)  # unit price snapshot
    qty = Column(Integer, nullable=False, default=1)

    order = relationship("EthioOrder", back_populates="items")

    def to_dict(self):
        return {
            "name": self.name,
            "price": float(self.price) if self.price is not None else None,
            "qty": self.qty,
        }
