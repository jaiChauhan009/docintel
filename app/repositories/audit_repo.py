from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id: uuid.UUID | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        detail: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            request_id=request_id,
            ip_address=ip_address,
            detail=detail or {},
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
