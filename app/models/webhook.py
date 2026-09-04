from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import WebhookDeliveryStatus


class Webhook(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhooks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Used to sign deliveries (HMAC-SHA256 in the X-DocIntel-Signature header).
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: ["document.processed"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    deliveries = relationship(
        "WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan"
    )


class WebhookDelivery(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webhook_deliveries"

    webhook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(
        String(16), default=WebhookDeliveryStatus.PENDING, nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    webhook = relationship("Webhook", back_populates="deliveries")
