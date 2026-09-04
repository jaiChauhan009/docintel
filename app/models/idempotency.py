from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class IdempotencyKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Maps (user, Idempotency-Key, request fingerprint) -> the document that was created.

    A DB-level unique constraint is the source of truth; Redis is only a fast-path cache.
    """

    __tablename__ = "idempotency_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_id_key"),)
