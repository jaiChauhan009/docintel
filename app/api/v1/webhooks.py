from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.schemas.webhook import WebhookCreate, WebhookCreated, WebhookOut
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED)
async def create_webhook(payload: WebhookCreate, user: CurrentUser, session: SessionDep):
    service = WebhookService(session)
    hook = await service.create(user, url=str(payload.url), event_types=payload.event_types)
    return WebhookCreated(
        id=hook.id,
        url=hook.url,
        event_types=hook.event_types,
        is_active=hook.is_active,
        created_at=hook.created_at,
        secret=hook.secret,
    )


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(user: CurrentUser, session: SessionDep):
    service = WebhookService(session)
    return await service.list(user)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    service = WebhookService(session)
    await service.delete(user, webhook_id)
