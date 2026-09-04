import pytest
from sqlalchemy import func, select

from app.db.session import SessionFactory
from app.models import Document
from tests.conftest import upload_file

pytestmark = pytest.mark.asyncio


async def _doc_count() -> int:
    async with SessionFactory() as s:
        return int(await s.scalar(select(func.count()).select_from(Document)) or 0)


async def test_same_key_same_body_is_replayed(client, auth, event_bus):
    headers = {**auth["headers"], "Idempotency-Key": "abc-123"}

    first = await client.post("/api/v1/documents", headers=headers, files=upload_file())
    second = await client.post("/api/v1/documents", headers=headers, files=upload_file())

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True

    assert await _doc_count() == 1
    # only ONE processing job published
    assert len(event_bus.published) == 1


async def test_same_key_different_body_conflicts(client, auth):
    headers = {**auth["headers"], "Idempotency-Key": "key-xyz"}
    await client.post("/api/v1/documents", headers=headers, files=upload_file())
    resp = await client.post(
        "/api/v1/documents",
        headers=headers,
        files=upload_file("other.txt", b"totally different content"),
    )
    assert resp.status_code == 409


async def test_no_key_creates_distinct_documents(client, auth):
    await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    assert await _doc_count() == 2


async def test_key_is_scoped_per_user(client, auth, user_factory):
    other = await user_factory()
    a = await client.post(
        "/api/v1/documents",
        headers={**auth["headers"], "Idempotency-Key": "shared"},
        files=upload_file(),
    )
    b = await client.post(
        "/api/v1/documents",
        headers={**other["headers"], "Idempotency-Key": "shared"},
        files=upload_file(),
    )
    assert a.json()["id"] != b.json()["id"]
    assert await _doc_count() == 2
