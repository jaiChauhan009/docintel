from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel

from app.schemas.common import ORMModel


class DocumentOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    file_name: str
    file_type: str
    file_size: int
    document_type: str
    status: str
    confidence: float | None
    error_message: str | None
    retry_count: int
    created_at: dt.datetime
    updated_at: dt.datetime
    processing_started_at: dt.datetime | None
    processing_completed_at: dt.datetime | None


class ProcessingAttemptOut(ORMModel):
    attempt_number: int
    status: str
    stage: str | None
    error_type: str | None
    error_message: str | None
    duration_ms: int | None
    created_at: dt.datetime


class DocumentDetailOut(DocumentOut):
    attempts: list[ProcessingAttemptOut] = []


class DocumentResultOut(BaseModel):
    document_id: uuid.UUID
    status: str
    document_type: str
    confidence: float
    extracted_data: dict
    masked_data: dict
    error_message: str | None = None


class UploadAccepted(BaseModel):
    id: uuid.UUID
    status: str
    document_type: str
    message: str = "document accepted for processing"
    idempotent_replay: bool = False
