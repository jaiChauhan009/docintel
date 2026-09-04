from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Header, Query, UploadFile, status

from app.api.deps import CurrentUser, RequestIdDep, SessionDep
from app.core.exceptions import NotFoundError
from app.schemas.common import Page
from app.schemas.document import (
    DocumentDetailOut,
    DocumentOut,
    DocumentResultOut,
    UploadAccepted,
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=UploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    user: CurrentUser,
    session: SessionDep,
    request_id: RequestIdDep,
    file: Annotated[UploadFile, File(...)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    content = await file.read()
    service = DocumentService(session)
    result = await service.upload(
        user=user,
        content=content,
        content_type=file.content_type or "application/octet-stream",
        filename=file.filename or "upload.bin",
        idempotency_key=idempotency_key,
        request_id=request_id,
    )
    doc = result.document
    return UploadAccepted(
        id=doc.id,
        status=doc.status,
        document_type=doc.document_type,
        idempotent_replay=result.replayed,
    )


@router.get("", response_model=Page[DocumentOut])
async def list_documents(
    user: CurrentUser,
    session: SessionDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    document_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    service = DocumentService(session)
    items, total = await service.list(
        user, status=status_filter, document_type=document_type, limit=limit, offset=offset
    )
    return Page[DocumentOut](
        items=[DocumentOut.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetailOut)
async def get_document(document_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    service = DocumentService(session)
    doc = await service.get(document_id, user)
    return DocumentDetailOut.model_validate(doc)


@router.get("/{document_id}/result", response_model=DocumentResultOut)
async def get_document_result(document_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    service = DocumentService(session)
    doc, result = await service.get_result(document_id, user)
    if result is None:
        return DocumentResultOut(
            document_id=doc.id,
            status=doc.status,
            document_type=doc.document_type,
            confidence=doc.confidence or 0.0,
            extracted_data={},
            masked_data={},
            error_message=doc.error_message,
        )
    return DocumentResultOut(
        document_id=doc.id,
        status=doc.status,
        document_type=result.document_type,
        confidence=result.confidence,
        extracted_data=result.extracted_data,
        masked_data=result.masked_data,
        error_message=doc.error_message,
    )


@router.post("/{document_id}/retry", response_model=DocumentOut)
async def retry_document(
    document_id: uuid.UUID, user: CurrentUser, session: SessionDep, request_id: RequestIdDep
):
    service = DocumentService(session)
    doc = await service.retry(document_id, user, request_id=request_id)
    return DocumentOut.model_validate(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID, user: CurrentUser, session: SessionDep, request_id: RequestIdDep
):
    service = DocumentService(session)
    await service.delete(document_id, user, request_id=request_id)
