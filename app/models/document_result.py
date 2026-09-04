from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_results"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)

    # Validated, schema-conforming structured extraction.
    extracted_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # A redacted copy safe to hand to less-trusted consumers / logs.
    masked_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    ocr_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_char_count: Mapped[int | None] = mapped_column(nullable=True)

    document = relationship("Document", back_populates="result")
