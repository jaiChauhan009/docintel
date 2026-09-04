from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID, key: str) -> IdempotencyKey | None:
        res = await self.session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
            )
        )
        return res.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        key: str,
        request_fingerprint: str,
        document_id: uuid.UUID,
    ) -> IdempotencyKey:
        row = IdempotencyKey(
            user_id=user_id,
            key=key,
            request_fingerprint=request_fingerprint,
            document_id=document_id,
        )
        self.session.add(row)
        await self.session.flush()
        return row
