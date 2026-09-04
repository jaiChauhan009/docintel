import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import UpstreamError
from app.db.session import SessionFactory
from app.integrations.llm.base import LLMClient, LLMResponse
from app.integrations.ocr.base import OcrResult, OCRProvider
from app.models import Document, ProcessingAttempt
from tests.conftest import upload_file

pytestmark = pytest.mark.asyncio


async def _attempts(doc_id):
    doc_id = uuid.UUID(str(doc_id))
    async with SessionFactory() as s:
        rows = (
            await s.execute(
                select(ProcessingAttempt).where(ProcessingAttempt.document_id == doc_id)
            )
        ).scalars().all()
        return list(rows)


async def _doc(doc_id):
    async with SessionFactory() as s:
        return await s.get(Document, uuid.UUID(str(doc_id)))


class GoodOCR(OCRProvider):
    name = "good"

    async def extract_text(self, content, mime_type, *, filename):
        text = content.decode()
        return OcrResult(text=text, provider=self.name, char_count=len(text), mean_confidence=0.9)


class FlakyOCR(OCRProvider):
    name = "flaky"

    def __init__(self, fail_times: int):
        self.calls = 0
        self.fail_times = fail_times

    async def extract_text(self, content, mime_type, *, filename):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise UpstreamError(f"transient failure #{self.calls}")
        text = content.decode()
        return OcrResult(text=text, provider=self.name, char_count=len(text), mean_confidence=0.9)


async def test_transient_failure_then_success(client, auth, worker):
    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]

    outcomes = await worker.drain(ocr=FlakyOCR(fail_times=1))
    assert outcomes[-1] == "COMPLETED"

    attempts = await _attempts(doc_id)
    assert len(attempts) == 2
    assert [a.status for a in sorted(attempts, key=lambda x: x.attempt_number)] == ["failed", "succeeded"]


async def test_persistent_failure_exhausts_and_marks_failed(client, auth, worker):
    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]

    outcomes = await worker.drain(ocr=FlakyOCR(fail_times=99))
    assert outcomes[-1] == "FAILED"

    doc = await _doc(doc_id)
    assert doc.status == "FAILED"
    assert doc.retry_count == 3
    assert doc.error_message

    attempts = await _attempts(doc_id)
    assert len(attempts) == 3
    assert all(a.status == "failed" for a in attempts)


async def test_non_retryable_validation_error_fails_immediately(client, auth, worker):
    up = await client.post(
        "/api/v1/documents", headers=auth["headers"], files=upload_file("blank.txt", b"   \n  ")
    )
    doc_id = up.json()["id"]

    outcomes = await worker.drain(ocr=GoodOCR())
    assert outcomes == ["FAILED"]
    attempts = await _attempts(doc_id)
    assert len(attempts) == 1
    assert attempts[0].stage == "ocr"


async def test_malformed_llm_output_is_not_retried(client, auth, worker):
    class JunkLLM(LLMClient):
        provider = "junk"
        model = "junk"

        async def complete_json(self, system_prompt, user_prompt):
            return LLMResponse(content="<html>not json</html>", provider="junk", model="junk")

    up = await client.post("/api/v1/documents", headers=auth["headers"], files=upload_file())
    doc_id = up.json()["id"]

    outcomes = await worker.drain(ocr=GoodOCR(), llm=JunkLLM())
    assert outcomes == ["FAILED"]
    attempts = await _attempts(doc_id)
    assert len(attempts) == 1
    assert attempts[0].stage == "validate"
