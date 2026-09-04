"""Strict extraction schemas.

The LLM is instructed to return JSON matching exactly one of these. The output is
**untrusted**: we parse it defensively (see ``services.processing_service``) and
then validate it here. Anything that does not validate causes the attempt to fail.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DocumentType


class _Strict(BaseModel):
    # Reject unknown keys so a hallucinated field can't silently pass through.
    model_config = ConfigDict(extra="forbid")


def _clamp_confidence(v: object) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, f))


class _WithConfidence(_Strict):
    confidence: float = 0.0

    @field_validator("confidence", mode="before")
    @classmethod
    def _v_confidence(cls, v: object) -> float:
        return _clamp_confidence(v)


# --------------------------------------------------------------------------- #
# Invoice
# --------------------------------------------------------------------------- #
class InvoiceLineItem(_Strict):
    description: str = ""
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None


class InvoiceExtraction(_WithConfidence):
    document_type: Literal[DocumentType.INVOICE] = DocumentType.INVOICE
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Receipt
# --------------------------------------------------------------------------- #
class ReceiptExtraction(_WithConfidence):
    document_type: Literal[DocumentType.RECEIPT] = DocumentType.RECEIPT
    merchant_name: str | None = None
    transaction_date: str | None = None
    currency: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    payment_method: str | None = None


# --------------------------------------------------------------------------- #
# Bank statement
# --------------------------------------------------------------------------- #
class BankTransaction(_Strict):
    date: str | None = None
    description: str | None = None
    amount: float | None = None
    type: Literal["credit", "debit", "unknown"] = "unknown"

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_type(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        return s if s in {"credit", "debit", "unknown"} else "unknown"


class BankStatementExtraction(_WithConfidence):
    document_type: Literal[DocumentType.BANK_STATEMENT] = DocumentType.BANK_STATEMENT
    account_holder: str | None = None
    account_number_masked: str | None = None
    bank_name: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None
    transactions: list[BankTransaction] = Field(default_factory=list)

    @field_validator("account_number_masked", mode="after")
    @classmethod
    def _force_mask(cls, v: str | None) -> str | None:
        """Never persist a full account number even if the model returns one."""
        if not v:
            return v
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) <= 4:
            return v
        return "****" + digits[-4:]


# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
class ContractParty(_Strict):
    name: str | None = None
    role: str | None = None


class ContractExtraction(_WithConfidence):
    document_type: Literal[DocumentType.CONTRACT] = DocumentType.CONTRACT
    parties: list[ContractParty] = Field(default_factory=list)
    effective_date: str | None = None
    expiration_date: str | None = None
    contract_value: float | None = None
    currency: str | None = None
    obligations: list[str] = Field(default_factory=list)
    important_dates: list[str] = Field(default_factory=list)
    termination_clauses: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Unknown (fallback)
# --------------------------------------------------------------------------- #
class UnknownExtraction(_WithConfidence):
    document_type: Literal[DocumentType.UNKNOWN] = DocumentType.UNKNOWN
    summary: str | None = None


SCHEMA_BY_TYPE: dict[DocumentType, type[_WithConfidence]] = {
    DocumentType.INVOICE: InvoiceExtraction,
    DocumentType.RECEIPT: ReceiptExtraction,
    DocumentType.BANK_STATEMENT: BankStatementExtraction,
    DocumentType.CONTRACT: ContractExtraction,
    DocumentType.UNKNOWN: UnknownExtraction,
}


def schema_for(document_type: str | DocumentType) -> type[_WithConfidence]:
    try:
        return SCHEMA_BY_TYPE.get(DocumentType(document_type), UnknownExtraction)
    except ValueError:
        return UnknownExtraction
