import pytest

from app.models.enums import ALLOWED_STATUS_TRANSITIONS, DocumentStatus
from tests.conftest import upload_file



def test_transition_table_is_sane():
    t = ALLOWED_STATUS_TRANSITIONS
    assert DocumentStatus.PROCESSING in t[DocumentStatus.UPLOADED]
    assert t[DocumentStatus.PROCESSING] >= {DocumentStatus.COMPLETED, DocumentStatus.FAILED}
    assert t[DocumentStatus.COMPLETED] == set()  # terminal
    assert DocumentStatus.PROCESSING in t[DocumentStatus.FAILED]  # manual retry allowed


async def test_happy_path_transitions(client, auth, worker):
    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]
    assert up.json()["status"] == "UPLOADED"

    await worker.drain()
    got = await client.get(f"/api/v1/documents/{doc_id}", headers=auth["headers"])
    assert got.json()["status"] == "COMPLETED"


async def test_cannot_retry_completed_document(client, auth, worker):
    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]
    await worker.drain()
    resp = await client.post(f"/api/v1/documents/{doc_id}/retry", headers=auth["headers"])
    assert resp.status_code == 422


async def test_failed_document_can_be_retried(client, auth, worker):
    from app.core.exceptions import UpstreamError
    from app.integrations.ocr.base import OCRProvider

    class AlwaysFailOCR(OCRProvider):
        name = "boom"

        async def extract_text(self, *a, **k):
            raise UpstreamError("ocr down")

    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]
    await worker.drain(ocr=AlwaysFailOCR())

    got = await client.get(f"/api/v1/documents/{doc_id}", headers=auth["headers"])
    assert got.json()["status"] == "FAILED"

    retry = await client.post(f"/api/v1/documents/{doc_id}/retry", headers=auth["headers"])
    assert retry.status_code == 200
    assert retry.json()["status"] in {"UPLOADED", "PROCESSING"}

    # this time succeed
    await worker.drain()
    final = await client.get(f"/api/v1/documents/{doc_id}", headers=auth["headers"])
    assert final.json()["status"] == "COMPLETED"
