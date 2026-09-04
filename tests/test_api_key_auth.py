import pytest
from sqlalchemy import select

from app.db.session import SessionFactory
from app.models import ApiKey
from tests.conftest import upload_file

pytestmark = pytest.mark.asyncio


async def test_create_key_returns_raw_once_and_stores_only_hash(client, auth):
    resp = await client.post(
        "/api/v1/api-keys", headers=auth["headers"], json={"name": "ci-pipeline"}
    )
    assert resp.status_code == 201
    body = resp.json()
    raw = body["api_key"]
    assert raw.startswith("dik_")
    assert body["key_prefix"] == raw[:12]

    async with SessionFactory() as s:
        row = (await s.execute(select(ApiKey))).scalar_one()
        assert row.key_hash != raw
        assert len(row.key_hash) == 64  # sha256 hex
        assert raw not in row.key_hash

    listed = await client.get("/api/v1/api-keys", headers=auth["headers"])
    assert "api_key" not in listed.json()[0]
    assert listed.json()[0]["key_prefix"] == raw[:12]


async def test_api_key_authenticates_requests(client, auth):
    resp = await client.post(
        "/api/v1/api-keys", headers=auth["headers"], json={"name": "svc"}
    )
    raw = resp.json()["api_key"]

    # upload using ONLY the api key
    up = await client.post(
        "/api/v1/documents", headers={"X-API-Key": raw}, files=upload_file()
    )
    assert up.status_code == 202

    listed = await client.get("/api/v1/documents", headers={"X-API-Key": raw})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


async def test_revoked_key_is_rejected(client, auth):
    resp = await client.post(
        "/api/v1/api-keys", headers=auth["headers"], json={"name": "temp"}
    )
    raw = resp.json()["api_key"]
    key_id = resp.json()["id"]

    assert (await client.get("/api/v1/documents", headers={"X-API-Key": raw})).status_code == 200
    assert (
        await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth["headers"])
    ).status_code == 204
    assert (await client.get("/api/v1/documents", headers={"X-API-Key": raw})).status_code == 401


async def test_unknown_key_rejected(client):
    assert (
        await client.get("/api/v1/documents", headers={"X-API-Key": "dik_bogus"})
    ).status_code == 401
