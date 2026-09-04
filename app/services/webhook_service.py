from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.metrics import webhook_deliveries_total
from app.models import User, Webhook, WebhookDelivery
from app.models.enums import WebhookDeliveryStatus
from app.repositories.webhook_repo import WebhookRepository

log = get_logger(__name__)


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _backoff_seconds(attempt: int) -> int:
    # 1 -> base^1, 2 -> base^2, ... capped at 1 hour
    return min(settings.webhook_backoff_base_seconds**attempt, 3600)


class WebhookService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = WebhookRepository(session)

    # --- CRUD ----------------------------------------------------------
    async def create(self, user: User, *, url: str, event_types: list[str]) -> Webhook:
        return await self.repo.create(
            user_id=user.id,
            url=url,
            secret=secrets.token_urlsafe(24),
            event_types=event_types or ["document.processed"],
        )

    async def list(self, user: User) -> list[Webhook]:
        return await self.repo.list_for_user(user.id)

    async def delete(self, user: User, webhook_id: uuid.UUID) -> None:
        hook = await self.repo.get(webhook_id)
        if hook is None or hook.user_id != user.id:
            raise NotFoundError("webhook not found")
        await self.repo.delete(hook)

    # --- delivery ----------------------------------------------------------
    async def enqueue_document_processed(
        self, *, user_id: uuid.UUID, document_id: uuid.UUID, status: str
    ) -> list[WebhookDelivery]:
        event_type = "document.processed"
        hooks = await self.repo.list_active_for_user_event(user_id, event_type)
        payload = {
            "event": event_type,
            "document_id": str(document_id),
            "status": status.lower(),
        }
        deliveries: list[WebhookDelivery] = []
        for hook in hooks:
            delivery = await self.repo.create_delivery(
                webhook_id=hook.id,
                document_id=document_id,
                event_type=event_type,
                payload=payload,
                status=WebhookDeliveryStatus.PENDING,
                next_retry_at=dt.datetime.now(dt.timezone.utc),
            )
            deliveries.append(delivery)
        await self.session.flush()
        # Best-effort immediate attempt; anything still pending is picked up by the loop.
        for delivery in deliveries:
            await self.attempt_delivery(delivery)
        return deliveries

    async def attempt_delivery(self, delivery: WebhookDelivery) -> WebhookDelivery:
        hook = await self.repo.get(delivery.webhook_id)
        if hook is None or not hook.is_active:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.last_error = "webhook removed or inactive"
            return delivery

        body = json.dumps(delivery.payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "DocIntel-Webhook/1",
            "X-DocIntel-Event": delivery.event_type,
            "X-DocIntel-Delivery": str(delivery.id),
            "X-DocIntel-Signature": f"sha256={_sign(hook.secret, body)}",
        }
        delivery.attempts += 1
        try:
            async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
                resp = await client.post(hook.url, content=body, headers=headers)
            delivery.last_status_code = resp.status_code
            if 200 <= resp.status_code < 300:
                delivery.status = WebhookDeliveryStatus.DELIVERED
                delivery.delivered_at = dt.datetime.now(dt.timezone.utc)
                delivery.next_retry_at = None
                delivery.last_error = None
                webhook_deliveries_total.labels(outcome="delivered").inc()
                return delivery
            delivery.last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:  # noqa: BLE001
            delivery.last_error = str(exc)[:200]

        # Failure path -> schedule retry or give up.
        if delivery.attempts >= settings.webhook_max_attempts:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.next_retry_at = None
            webhook_deliveries_total.labels(outcome="failed").inc()
        else:
            delay = _backoff_seconds(delivery.attempts)
            delivery.status = WebhookDeliveryStatus.PENDING
            delivery.next_retry_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=delay)
            webhook_deliveries_total.labels(outcome="retry_scheduled").inc()
        return delivery

    async def process_due(self, *, limit: int = 50) -> int:
        now = dt.datetime.now(dt.timezone.utc)
        due = await self.repo.due_deliveries(now, limit=limit)
        for delivery in due:
            await self.attempt_delivery(delivery)
        await self.session.flush()
        return len(due)
