from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.security import generate_api_key
from app.models import ApiKey, User
from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.audit_repo import AuditLogRepository


class ApiKeyService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ApiKeyRepository(session)
        self.audit = AuditLogRepository(session)

    async def create(self, user: User, *, name: str, request_id: str | None = None) -> tuple[ApiKey, str]:
        raw, key_hash, prefix = generate_api_key()
        api_key = await self.repo.create(
            user_id=user.id, name=name, key_hash=key_hash, key_prefix=prefix
        )
        await self.audit.record(
            action="api_key.create",
            resource_type="api_key",
            resource_id=str(api_key.id),
            user_id=user.id,
            request_id=request_id,
        )
        return api_key, raw

    async def list(self, user: User) -> list[ApiKey]:
        return await self.repo.list_for_user(user.id)

    async def revoke(self, user: User, api_key_id: uuid.UUID, *, request_id: str | None = None) -> None:
        api_key = await self.repo.get(api_key_id)
        if api_key is None or api_key.user_id != user.id:
            raise NotFoundError("api key not found")
        if api_key.revoked_at is None:
            api_key.revoked_at = dt.datetime.now(dt.timezone.utc)
        await self.audit.record(
            action="api_key.revoke",
            resource_type="api_key",
            resource_id=str(api_key_id),
            user_id=user.id,
            request_id=request_id,
        )
