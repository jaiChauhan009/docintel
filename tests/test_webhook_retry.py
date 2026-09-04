import datetime as dt

import pytest
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models import Webhook, WebhookDelivery
from app.models.enums import WebhookDeliveryStatus
from app.services.webhook_service import WebhookService

pytestmark = pytest.mark.asyncio


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = "ok" if status_code < 300 else "boom"


class _FakeAsyncClient:
    """Drop-in for httpx.AsyncClient. ``script`` is a list of status codes."""

    script: list[int] = []
    calls: list[dict] = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, content=None, headers=None):
        _FakeAsyncClient.calls.append({"url": url, "headers": headers, "body": content})
        idx = len(_FakeAsyncClient.calls) - 1
        code = _FakeAsyncClient.script[idx] if idx < len(_FakeAsyncClient.script) else _FakeAsyncClient.script[-1]
        return _FakeResponse(code)


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch):
    _FakeAsyncClient.script = [200]
    _FakeAsyncClient.calls = []
    monkeypatch.setattr("app.services.webhook_service.httpx.AsyncClient", _FakeAsyncClient)
    yield


async def _make_user_and_webhook(client, auth):
    resp = await client.post(
        "/api/v1/webhooks",
        headers=auth["headers"],
        json={"url": "https://example.test/hook", "event_types": ["document.processed"]},
    )
    assert resp.status_code == 201
    return resp.json()


async def test_successful_delivery_first_try(client, auth):
    hook = await _make_user_and_webhook(client, auth)
    _FakeAsyncClient.script = [200]

    async with SessionFactory() as s:
        svc = WebhookService(s)
        wh = (await s.execute(select(Webhook))).scalar_one()
        deliveries = await svc.enqueue_document_processed(
            user_id=wh.user_id, document_id=wh.id, status="COMPLETED"
        )
        await s.commit()

    assert len(deliveries) == 1
    async with SessionFactory() as s:
        d = (await s.execute(select(WebhookDelivery))).scalar_one()
        assert d.status == WebhookDeliveryStatus.DELIVERED
        assert d.attempts == 1
        assert d.delivered_at is not None
    # signature header present
    assert _FakeAsyncClient.calls[0]["headers"]["X-DocIntel-Signature"].startswith("sha256=")


async def test_retries_with_backoff_then_succeeds(client, auth):
    await _make_user_and_webhook(client, auth)
    _FakeAsyncClient.script = [500, 503, 200]

    async with SessionFactory() as s:
        wh = (await s.execute(select(Webhook))).scalar_one()
        svc = WebhookService(s)
        await svc.enqueue_document_processed(
            user_id=wh.user_id, document_id=wh.id, status="COMPLETED"
        )
        await s.commit()

    # after first (failed) attempt -> pending with a scheduled retry
    async with SessionFactory() as s:
        d = (await s.execute(select(WebhookDelivery))).scalar_one()
        assert d.status == WebhookDeliveryStatus.PENDING
        assert d.attempts == 1
        assert d.next_retry_at is not None
        d.next_retry_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        await s.commit()

    # process due -> second attempt (503) still pending
    async with SessionFactory() as s:
        svc = WebhookService(s)
        assert await svc.process_due() == 1
        await s.commit()
    async with SessionFactory() as s:
        d = (await s.execute(select(WebhookDelivery))).scalar_one()
        assert d.attempts == 2
        assert d.status == WebhookDeliveryStatus.PENDING
        d.next_retry_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        await s.commit()

    # process due -> third attempt (200) delivered
    async with SessionFactory() as s:
        svc = WebhookService(s)
        await svc.process_due()
        await s.commit()
    async with SessionFactory() as s:
        d = (await s.execute(select(WebhookDelivery))).scalar_one()
        assert d.status == WebhookDeliveryStatus.DELIVERED
        assert d.attempts == 3


async def test_gives_up_after_max_attempts(client, auth, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "webhook_max_attempts", 3)
    await _make_user_and_webhook(client, auth)
    _FakeAsyncClient.script = [500]

    async with SessionFactory() as s:
        wh = (await s.execute(select(Webhook))).scalar_one()
        svc = WebhookService(s)
        await svc.enqueue_document_processed(
            user_id=wh.user_id, document_id=wh.id, status="COMPLETED"
        )
        await s.commit()

    for _ in range(5):
        async with SessionFactory() as s:
            d = (await s.execute(select(WebhookDelivery))).scalar_one()
            if d.status == WebhookDeliveryStatus.FAILED:
                break
            d.next_retry_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
            await s.commit()
        async with SessionFactory() as s:
            svc = WebhookService(s)
            await svc.process_due()
            await s.commit()

    async with SessionFactory() as s:
        d = (await s.execute(select(WebhookDelivery))).scalar_one()
        assert d.status == WebhookDeliveryStatus.FAILED
        assert d.attempts == 3
