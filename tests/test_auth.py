import pytest

pytestmark = pytest.mark.asyncio


async def test_register_returns_token(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "supersecret1", "full_name": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


async def test_register_duplicate_email_conflicts(client):
    payload = {"email": "dup@example.com", "password": "supersecret1"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["error"] == "conflict"


async def test_register_rejects_short_password(client):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "x@example.com", "password": "short"}
    )
    assert resp.status_code == 422


async def test_login_success_and_failure(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "supersecret1"},
    )
    ok = await client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "supersecret1"}
    )
    assert ok.status_code == 200 and ok.json()["access_token"]

    bad = await client.post(
        "/api/v1/auth/login", json={"email": "bob@example.com", "password": "wrongpass1"}
    )
    assert bad.status_code == 401


async def test_me_requires_auth(client, auth):
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    resp = await client.get("/api/v1/auth/me", headers=auth["headers"])
    assert resp.status_code == 200
    assert resp.json()["email"] == auth["email"]


async def test_invalid_token_rejected(client):
    resp = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert resp.status_code == 401
