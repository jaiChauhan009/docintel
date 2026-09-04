from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Webhook, WebhookDelivery
from app.models.enums import WebhookDeliveryStatus


class WebhookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, user_id: uuid.UUID, url: str, secret: str, event_types: list[str]) -> Webhook:
        hook = Webhook(user_id=user_id, url=url, secret=secret, event_types=event_types)
        self.session.add(hook)
        await self.session.flush()
        return hook

    async def get(self, webhook_id: uuid.UUID) -> Webhook | None:
        return await self.session.get(Webhook, webhook_id)

    async def list_for_user(self, user_id: uuid.UUID) -> list[Webhook]:
        res = await self.session.execute(
            select(Webhook).where(Webhook.user_id == user_id).order_by(Webhook.created_at.desc())
        )
        return list(res.scalars().all())

    async def list_active_for_user_event(self, user_id: uuid.UUID, event_type: str) -> list[Webhook]:
        res = await self.session.execute(
            select(Webhook).where(Webhook.user_id == user_id, Webhook.is_active.is_(True))
        )
        return [h for h in res.scalars().all() if event_type in (h.event_types or [])]

    async def delete(self, hook: Webhook) -> None:
        await self.session.delete(hook)

    # --- deliveries ----------------------------------------------------------
    async def create_delivery(self, **fields) -> WebhookDelivery:
        delivery = WebhookDelivery(**fields)
        self.session.add(delivery)
        await self.session.flush()
        return delivery

    async def get_delivery(self, delivery_id: uuid.UUID) -> WebhookDelivery | None:
        return await self.session.get(WebhookDelivery, delivery_id)

    async def due_deliveries(self, now: dt.datetime, limit: int = 50) -> list[WebhookDelivery]:
        res = await self.session.execute(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                WebhookDelivery.next_retry_at <= now,
            )
            .order_by(WebhookDelivery.next_retry_at)
            .limit(limit)
        )
        return list(res.scalars().all())
