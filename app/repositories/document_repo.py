from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **kwargs) -> Document:
        doc = Document(**kwargs)
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get(self, document_id: uuid.UUID) -> Document | None:
        return await self.session.get(Document, document_id)

    async def get_with_attempts(self, document_id: uuid.UUID) -> Document | None:
        res = await self.session.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.attempts))
        )
        return res.scalar_one_or_none()

    async def get_with_result(self, document_id: uuid.UUID) -> Document | None:
        res = await self.session.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.result))
        )
        return res.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        status: str | None = None,
        document_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        conditions = [Document.user_id == user_id]
        if status:
            conditions.append(Document.status == status)
        if document_type:
            conditions.append(Document.document_type == document_type)

        total = await self.session.scalar(
            select(func.count()).select_from(Document).where(*conditions)
        )
        res = await self.session.execute(
            select(Document)
            .where(*conditions)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all()), int(total or 0)

    async def find_by_idempotency(
        self, user_id: uuid.UUID, idempotency_key: str
    ) -> Document | None:
        res = await self.session.execute(
            select(Document).where(
                Document.user_id == user_id,
                Document.idempotency_key == idempotency_key,
            )
        )
        return res.scalars().first()

    async def find_by_checksum(
        self, user_id: uuid.UUID, checksum: str
    ) -> Document | None:
        res = await self.session.execute(
            select(Document)
            .where(Document.user_id == user_id, Document.checksum_sha256 == checksum)
            .order_by(Document.created_at.desc())
        )
        return res.scalars().first()

    async def delete(self, doc: Document) -> None:
        await self.session.delete(doc)
