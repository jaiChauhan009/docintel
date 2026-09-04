from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, RequestIdDep, SessionDep
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate, user: CurrentUser, session: SessionDep, request_id: RequestIdDep
):
    service = ApiKeyService(session)
    api_key, raw = await service.create(user, name=payload.name, request_id=request_id)
    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        revoked_at=api_key.revoked_at,
        api_key=raw,
    )


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(user: CurrentUser, session: SessionDep):
    service = ApiKeyService(session)
    return await service.list(user)


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: uuid.UUID, user: CurrentUser, session: SessionDep, request_id: RequestIdDep
):
    service = ApiKeyService(session)
    await service.revoke(user, api_key_id, request_id=request_id)
