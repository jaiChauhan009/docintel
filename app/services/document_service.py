from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.metrics import documents_uploaded_total
from app.integrations.events import DocumentEvent, get_event_publisher
from app.integrations.storage import get_storage
from app.models import Document, User
from app.models.enums import ALLOWED_STATUS_TRANSITIONS, DocumentStatus, DocumentType
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.document_repo import DocumentRepository
from app.repositories.idempotency_repo import IdempotencyRepository
from app.repositories.result_repo import DocumentResultRepository
from app.services.idempotency import request_fingerprint

log = get_logger(__name__)


class UploadResult:
    def __init__(self, document: Document, *, replayed: bool):
        self.document = document
        self.replayed = replayed


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.docs = DocumentRepository(session)
        self.results = DocumentResultRepository(session)
        self.idem = IdempotencyRepository(session)
        self.audit = AuditLogRepository(session)
        self.storage = get_storage()

    # --- validation --------------------------------------------------------
    @staticmethod
    def _validate_upload(*, content: bytes, content_type: str, filename: str) -> None:
        if not content:
            raise ValidationError("uploaded file is empty")
        if len(content) > settings.max_upload_size_bytes:
            raise ValidationError(
                f"file exceeds max size of {settings.max_upload_size_mb} MB"
            )
        allowed = settings.allowed_mime_type_set
        if content_type not in allowed:
            raise ValidationError(
                f"unsupported content type '{content_type}'. allowed: {sorted(allowed)}"
            )
        if not filename or len(filename) > 512:
            raise ValidationError("invalid file name")

    # --- upload ----------------------------------------------------------
    async def upload(
        self,
        *,
        user: User,
        content: bytes,
        content_type: str,
        filename: str,
        idempotency_key: str | None,
        request_id: str | None,
    ) -> UploadResult:
        self._validate_upload(content=content, content_type=content_type, filename=filename)
        checksum = hashlib.sha256(content).hexdigest()
        fingerprint = request_fingerprint(
            user_id=str(user.id),
            filename=filename,
            checksum=checksum,
            content_type=content_type,
        )

        # 1. Idempotency replay (explicit header wins).
        if idempotency_key:
            existing = await self.idem.get(user.id, idempotency_key)
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise ConflictError(
                        "Idempotency-Key already used with a different request body"
                    )
                doc = await self.docs.get(existing.document_id)
                if doc is not None:
                    log.info(
                        "idempotent upload replay",
                        fields={"document_id": str(doc.id), "idempotency_key": idempotency_key},
                    )
                    return UploadResult(doc, replayed=True)

        # 2. Persist the object first; the storage key embeds a fresh UUID.
        document_id = uuid.uuid4()
        storage_key = f"{user.id}/{document_id}/{filename}"
        await self.storage.put(storage_key, content, content_type)

        # 3. Create the document row (status UPLOADED).
        doc = await self.docs.create(
            id=document_id,
            user_id=user.id,
            file_name=filename,
            file_type=content_type,
            file_size=len(content),
            storage_key=storage_key,
            checksum_sha256=checksum,
            document_type=DocumentType.UNKNOWN,
            status=DocumentStatus.UPLOADED,
            idempotency_key=idempotency_key,
        )

        # 4. Record the idempotency mapping (unique constraint = source of truth).
        if idempotency_key:
            try:
                await self.idem.create(
                    user_id=user.id,
                    key=idempotency_key,
                    request_fingerprint=fingerprint,
                    document_id=doc.id,
                )
                await self.session.flush()
            except IntegrityError:
                await self.session.rollback()
                existing = await self.idem.get(user.id, idempotency_key)
                if existing:
                    replay = await self.docs.get(existing.document_id)
                    if replay:
                        return UploadResult(replay, replayed=True)
                raise

        await self.audit.record(
            action="document.upload",
            resource_type="document",
            resource_id=str(doc.id),
            user_id=user.id,
            request_id=request_id,
            detail={"file_type": content_type, "file_size": len(content)},
        )
        await self.session.flush()

        # 5. Publish the processing event AFTER the row is committed-safe.
        await self.session.commit()
        await self._publish_processing_event(doc, attempt=1, request_id=request_id)

        documents_uploaded_total.labels(document_hint="unknown").inc()
        return UploadResult(doc, replayed=False)

    async def _publish_processing_event(
        self, doc: Document, *, attempt: int, request_id: str | None
    ) -> None:
        publisher = get_event_publisher()
        await publisher.publish_document_event(
            DocumentEvent(
                document_id=str(doc.id),
                user_id=str(doc.user_id),
                event="document.uploaded",
                attempt=attempt,
                request_id=request_id,
            )
        )

    # --- reads -----------------------------------------------------------
    async def _owned(self, document_id: uuid.UUID, user: User) -> Document:
        doc = await self.docs.get(document_id)
        if doc is None:
            raise NotFoundError("document not found")
        if doc.user_id != user.id:
            # 404 (not 403) so we don't leak existence to other tenants.
            raise NotFoundError("document not found")
        return doc

    async def get(self, document_id: uuid.UUID, user: User) -> Document:
        await self._owned(document_id, user)
        doc = await self.docs.get_with_attempts(document_id)
        assert doc is not None
        return doc

    async def list(
        self,
        user: User,
        *,
        status: str | None,
        document_type: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Document], int]:
        return await self.docs.list_for_user(
            user.id, status=status, document_type=document_type, limit=limit, offset=offset
        )

    async def get_result(self, document_id: uuid.UUID, user: User):
        doc = await self._owned(document_id, user)
        result = await self.results.get_for_document(document_id)
        return doc, result

    async def delete(self, document_id: uuid.UUID, user: User, *, request_id: str | None) -> None:
        doc = await self._owned(document_id, user)
        try:
            await self.storage.delete(doc.storage_key)
        except Exception as exc:  # noqa: BLE001 - best-effort; row removal still proceeds
            log.warning("failed to delete object", fields={"error": str(exc)})
        await self.docs.delete(doc)
        await self.audit.record(
            action="document.delete",
            resource_type="document",
            resource_id=str(document_id),
            user_id=user.id,
            request_id=request_id,
        )

    async def retry(self, document_id: uuid.UUID, user: User, *, request_id: str | None) -> Document:
        doc = await self._owned(document_id, user)
        if doc.status not in {DocumentStatus.FAILED}:
            raise ValidationError(f"cannot retry a document in status {doc.status}")
        if DocumentStatus.PROCESSING not in ALLOWED_STATUS_TRANSITIONS[DocumentStatus(doc.status)]:
            raise ValidationError("retry not allowed from current state")

        doc.status = DocumentStatus.UPLOADED
        doc.error_message = None
        await self.session.flush()
        await self.audit.record(
            action="document.retry",
            resource_type="document",
            resource_id=str(document_id),
            user_id=user.id,
            request_id=request_id,
            detail={"retry_count": doc.retry_count},
        )
        await self.session.commit()
        await self._publish_processing_event(doc, attempt=doc.retry_count + 1, request_id=request_id)
        return doc
