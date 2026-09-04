from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProcessingAttempt


class ProcessingAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_for_document(self, document_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(ProcessingAttempt)
            .where(ProcessingAttempt.document_id == document_id)
        )
        return int(total or 0)

    async def create(self, **fields) -> ProcessingAttempt:
        attempt = ProcessingAttempt(**fields)
        self.session.add(attempt)
        await self.session.flush()
        return attempt

    async def list_for_document(self, document_id: uuid.UUID) -> list[ProcessingAttempt]:
        res = await self.session.execute(
            select(ProcessingAttempt)
            .where(ProcessingAttempt.document_id == document_id)
            .order_by(ProcessingAttempt.attempt_number)
        )
        return list(res.scalars().all())
