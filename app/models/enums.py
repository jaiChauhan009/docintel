from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentType(StrEnum):
    INVOICE = "invoice"
    RECEIPT = "receipt"
    CONTRACT = "contract"
    BANK_STATEMENT = "bank_statement"
    UNKNOWN = "unknown"


class AttemptStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class WebhookDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


# Allowed status transitions for a document. Enforced in the service layer.
ALLOWED_STATUS_TRANSITIONS: dict[DocumentStatus, set[DocumentStatus]] = {
    DocumentStatus.UPLOADED: {DocumentStatus.PROCESSING},
    DocumentStatus.PROCESSING: {
        DocumentStatus.COMPLETED,
        DocumentStatus.FAILED,
        DocumentStatus.PROCESSING,  # a fresh retry re-enters PROCESSING
    },
    # terminal-ish: FAILED can be manually retried back into PROCESSING
    DocumentStatus.FAILED: {DocumentStatus.PROCESSING},
    DocumentStatus.COMPLETED: set(),
}
