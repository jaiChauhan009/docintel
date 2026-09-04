from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentResult


class DocumentResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_for_document(self, document_id: uuid.UUID) -> DocumentResult | None:
        res = await self.session.execute(
            select(DocumentResult).where(DocumentResult.document_id == document_id)
        )
        return res.scalar_one_or_none()

    async def upsert(self, document_id: uuid.UUID, **fields) -> DocumentResult:
        existing = await self.get_for_document(document_id)
        if existing is None:
            existing = DocumentResult(document_id=document_id, **fields)
            self.session.add(existing)
        else:
            for key, value in fields.items():
                setattr(existing, key, value)
        await self.session.flush()
        return existing
