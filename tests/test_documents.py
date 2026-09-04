import pytest

from tests.conftest import upload_file

pytestmark = pytest.mark.asyncio


async def test_upload_creates_uploaded_document(client, auth, event_bus):
    resp = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "UPLOADED"
    assert body["idempotent_replay"] is False
    assert len(event_bus.published) == 1
    assert event_bus.published[0].document_id == body["id"]


async def test_upload_rejects_disallowed_mime(client, auth):
    files = {"file": ("evil.exe", b"MZ\x90\x00", "application/x-msdownload")}
    resp = await client.post("/api/v1/documents", headers=auth["headers"], files=files)
    assert resp.status_code == 422


async def test_upload_rejects_oversize(client, auth, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "max_upload_size_mb", 0)
    big = b"x" * 2048
    resp = await client.post(
        "/api/v1/documents", headers=auth["headers"], files={"file": ("a.txt", big, "text/plain")}
    )
    assert resp.status_code == 422


async def test_full_pipeline_completes(client, auth, worker):
    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]

    outcomes = await worker.drain()
    assert outcomes == ["COMPLETED"]

    got = await client.get(f"/api/v1/documents/{doc_id}", headers=auth["headers"])
    assert got.status_code == 200
    assert got.json()["status"] == "COMPLETED"
    assert got.json()["document_type"] == "invoice"
    assert len(got.json()["attempts"]) == 1

    result = await client.get(f"/api/v1/documents/{doc_id}/result", headers=auth["headers"])
    assert result.status_code == 200
    data = result.json()
    assert data["document_type"] == "invoice"
    assert data["extracted_data"]["invoice_number"] == "INV-2026-000481"
    assert data["extracted_data"]["total"] == 3924.0
    assert 0.0 <= data["confidence"] <= 1.0


async def test_list_documents_paginates_and_scopes(client, auth, user_factory):
    for _ in range(3):
        await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())

    other = await user_factory()
    await client.post("/api/v1/documents", headers=other["headers"], files=upload_file())

    resp = await client.get("/api/v1/documents?limit=2", headers=auth["headers"])
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_delete_document(client, auth):
    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]
    assert (await client.delete(f"/api/v1/documents/{doc_id}", headers=auth["headers"])).status_code == 204
    assert (await client.get(f"/api/v1/documents/{doc_id}", headers=auth["headers"])).status_code == 404
