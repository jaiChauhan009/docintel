from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApiKey


class ApiKeyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, user_id: uuid.UUID, name: str, key_hash: str, key_prefix: str) -> ApiKey:
        api_key = ApiKey(user_id=user_id, name=name, key_hash=key_hash, key_prefix=key_prefix)
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def get(self, api_key_id: uuid.UUID) -> ApiKey | None:
        return await self.session.get(ApiKey, api_key_id)

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        res = await self.session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        return res.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> list[ApiKey]:
        res = await self.session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc())
        )
        return list(res.scalars().all())
