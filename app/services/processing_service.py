"""The document-processing pipeline. Transport-agnostic: the Kafka worker and the
test-suite both call :meth:`DocumentProcessor.process_event`.

Lifecycle per event:
    UPLOADED --> PROCESSING --(ok)--> COMPLETED
                            \\-(err)-> retry (<=MAX) or FAILED

Every attempt is recorded in ``processing_attempts``. Retries use exponential
backoff; the delay is awaited before the follow-up event is re-published so the
broker stays simple (no delay-topic needed for the MVP).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import DocIntelError, UpstreamError, ValidationError
from app.core.logging import bind_context, get_logger
from app.core.metrics import (
    documents_failed_total,
    documents_processed_total,
    processing_duration_seconds,
)
from app.integrations.events import DocumentEvent, EventPublisher, get_event_publisher
from app.integrations.llm import LLMClient, get_llm_client
from app.integrations.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.integrations.ocr import OCRProvider, get_ocr_provider
from app.integrations.storage import ObjectStorage, get_storage
from app.models import Document
from app.models.enums import (
    ALLOWED_STATUS_TRANSITIONS,
    AttemptStatus,
    DocumentStatus,
    DocumentType,
)
from app.repositories.attempt_repo import ProcessingAttemptRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.result_repo import DocumentResultRepository
from app.services.classification import classify
from app.services.extraction_parser import validate_extraction
from app.services.masking import mask_extraction
from app.services.webhook_service import WebhookService

log = get_logger(__name__)


class _StageError(Exception):
    def __init__(self, stage: str, exc: Exception):
        super().__init__(str(exc))
        self.stage = stage
        self.original = exc


def _transition_allowed(current: str, target: DocumentStatus) -> bool:
    try:
        return target in ALLOWED_STATUS_TRANSITIONS[DocumentStatus(current)]
    except (KeyError, ValueError):
        return False


class DocumentProcessor:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ocr: OCRProvider | None = None,
        llm: LLMClient | None = None,
        storage: ObjectStorage | None = None,
        publisher: EventPublisher | None = None,
    ) -> None:
        self.session = session
        self.docs = DocumentRepository(session)
        self.results = DocumentResultRepository(session)
        self.attempts = ProcessingAttemptRepository(session)
        self.webhooks = WebhookService(session)
        self.ocr = ocr or get_ocr_provider()
        self.llm = llm or get_llm_client()
        self.storage = storage or get_storage()
        self.publisher = publisher or get_event_publisher()

    # ------------------------------------------------------------------ #
    async def process_event(self, event: dict) -> str:
        document_id = uuid.UUID(str(event["document_id"]))
        attempt_hint = int(event.get("attempt", 1))
        bind_context(document_id=str(document_id), processing_attempt=attempt_hint,
                     request_id=event.get("request_id"))

        doc = await self.docs.get(document_id)
        if doc is None:
            log.warning("processing event for unknown document")
            return "unknown"

        if doc.status == DocumentStatus.COMPLETED:
            log.info("document already completed, skipping")
            return doc.status
        if doc.status == DocumentStatus.PROCESSING:
            log.info("document already processing, skipping duplicate event")
            return doc.status

        return await self._run_pipeline(doc)

    # ------------------------------------------------------------------ #
    async def _run_pipeline(self, doc: Document) -> str:
        attempt_number = await self.attempts.count_for_document(doc.id) + 1
        bind_context(processing_attempt=attempt_number)

        if not _transition_allowed(doc.status, DocumentStatus.PROCESSING):
            log.warning("illegal transition to PROCESSING", fields={"from": doc.status})
            return doc.status

        started = time.monotonic()
        now = dt.datetime.now(dt.timezone.utc)
        doc.status = DocumentStatus.PROCESSING
        doc.processing_started_at = doc.processing_started_at or now
        attempt = await self.attempts.create(
            document_id=doc.id,
            attempt_number=attempt_number,
            status=AttemptStatus.STARTED,
            started_at=now,
        )
        await self.session.commit()

        stage = "download"
        try:
            content = await self._download(doc)

            stage = "ocr"
            ocr_result = await self.ocr.extract_text(
                content, doc.file_type, filename=doc.file_name
            )
            if not ocr_result.text.strip():
                raise ValidationError("OCR produced no text")

            stage = "classify"
            doc_type, class_conf = classify(ocr_result.text)
            doc.document_type = doc_type

            stage = "llm"
            llm_resp = await self.llm.complete_json(
                SYSTEM_PROMPT, build_user_prompt(doc_type, ocr_result.text)
            )

            stage = "validate"
            extracted, extract_conf = validate_extraction(llm_resp.content, doc_type)

            stage = "persist"
            confidence = round(
                min(
                    x for x in [extract_conf, ocr_result.mean_confidence or extract_conf] if x is not None
                ),
                4,
            ) if doc_type != DocumentType.UNKNOWN else extract_conf
            masked = mask_extraction(extracted)
            await self.results.upsert(
                doc.id,
                document_type=doc_type.value,
                confidence=confidence,
                extracted_data=extracted,
                masked_data=masked,
                ocr_provider=ocr_result.provider,
                llm_provider=llm_resp.provider,
                llm_model=llm_resp.model,
                ocr_char_count=ocr_result.char_count,
            )
        except Exception as exc:  # noqa: BLE001
            return await self._handle_failure(doc, attempt, stage, exc, started)

        # --- success -------------------------------------------------------
        if not _transition_allowed(doc.status, DocumentStatus.COMPLETED):
            log.warning("illegal transition to COMPLETED", fields={"from": doc.status})
        doc.status = DocumentStatus.COMPLETED
        doc.confidence = confidence
        doc.error_message = None
        doc.processing_completed_at = dt.datetime.now(dt.timezone.utc)

        duration = time.monotonic() - started
        attempt.status = AttemptStatus.SUCCEEDED
        attempt.stage = stage
        attempt.duration_ms = int(duration * 1000)
        attempt.finished_at = dt.datetime.now(dt.timezone.utc)

        processing_duration_seconds.observe(duration)
        documents_processed_total.labels(document_type=doc.document_type).inc()
        await self.session.commit()

        log.info("document processing completed",
                 fields={"document_type": doc.document_type, "confidence": confidence,
                         "duration_ms": attempt.duration_ms})

        await self._notify(doc)
        return doc.status

    # ------------------------------------------------------------------ #
    async def _download(self, doc: Document) -> bytes:
        try:
            return await self.storage.get(doc.storage_key)
        except Exception as exc:  # noqa: BLE001
            raise UpstreamError(f"failed to download document: {exc}") from exc

    async def _handle_failure(
        self, doc: Document, attempt, stage: str, exc: Exception, started: float
    ) -> str:
        duration = time.monotonic() - started
        is_retryable = isinstance(exc, UpstreamError) or not isinstance(exc, (ValidationError,))
        message = getattr(exc, "message", None) or str(exc)

        attempt.status = AttemptStatus.FAILED
        attempt.stage = stage
        attempt.error_type = type(exc).__name__
        attempt.error_message = message[:1000]
        attempt.duration_ms = int(duration * 1000)
        attempt.finished_at = dt.datetime.now(dt.timezone.utc)

        doc.retry_count = attempt.attempt_number
        max_attempts = settings.max_processing_attempts

        if attempt.attempt_number < max_attempts and is_retryable:
            # Back to UPLOADED so a fresh event can pick it up.
            doc.status = DocumentStatus.UPLOADED
            doc.error_message = f"[attempt {attempt.attempt_number}] {message[:400]}"
            await self.session.commit()

            delay = settings.retry_backoff_base_seconds ** attempt.attempt_number
            log.warning("processing attempt failed, scheduling retry",
                        fields={"stage": stage, "error": message[:200],
                                "next_attempt": attempt.attempt_number + 1, "delay_s": delay})
            await asyncio.sleep(min(delay, 30))
            await self.publisher.publish_document_event(
                DocumentEvent(
                    document_id=str(doc.id),
                    user_id=str(doc.user_id),
                    event="document.retry",
                    attempt=attempt.attempt_number + 1,
                )
            )
            return doc.status

        # Exhausted / non-retryable -> FAILED (terminal).
        doc.status = DocumentStatus.FAILED
        doc.error_message = message[:1000]
        doc.processing_completed_at = dt.datetime.now(dt.timezone.utc)
        documents_failed_total.labels(reason=stage).inc()
        await self.session.commit()

        log.error("document processing failed permanently",
                  fields={"stage": stage, "error": message[:200],
                          "attempts": attempt.attempt_number})
        await self._notify(doc)
        return doc.status

    async def _notify(self, doc: Document) -> None:
        try:
            await self.webhooks.enqueue_document_processed(
                user_id=doc.user_id, document_id=doc.id, status=doc.status
            )
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001 - webhook issues never fail processing
            log.warning("failed to enqueue webhook", fields={"error": str(exc)})
            await self.session.rollback()
