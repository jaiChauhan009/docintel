from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import DocumentStatus, DocumentType


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(128), nullable=False)  # MIME type
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    document_type: Mapped[str] = mapped_column(
        String(32), default=DocumentType.UNKNOWN, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default=DocumentStatus.UPLOADED, nullable=False, index=True
    )

    confidence: Mapped[float | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    processing_started_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    result = relationship(
        "DocumentResult",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    attempts = relationship(
        "ProcessingAttempt",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ProcessingAttempt.attempt_number",
    )

    __table_args__ = (
        Index("ix_documents_user_status", "user_id", "status"),
        Index("ix_documents_user_created", "user_id", "created_at"),
    )
