"""Keyword-scoring document classifier.

Cheap, deterministic, and good enough as a first pass. The LLM step still receives
the detected type and could override it in a future iteration.
"""
from __future__ import annotations

import re

from app.models.enums import DocumentType

_SIGNALS: dict[DocumentType, list[str]] = {
    DocumentType.INVOICE: [
        "invoice", "invoice number", "bill to", "amount due", "purchase order",
        "net 30", "remit to", "subtotal", "tax id",
    ],
    DocumentType.RECEIPT: [
        "receipt", "cash", "change due", "thank you for shopping", "cashier",
        "tender", "card ****", "merchant", "auth code", "pos",
    ],
    DocumentType.BANK_STATEMENT: [
        "statement period", "opening balance", "closing balance", "account number",
        "available balance", "transaction history", "sort code", "iban", "beginning balance",
    ],
    DocumentType.CONTRACT: [
        "agreement", "this agreement", "hereby", "party", "parties", "whereas",
        "shall", "termination", "governing law", "in witness whereof", "effective date",
    ],
}


def classify(text: str) -> tuple[DocumentType, float]:
    lowered = text.lower()
    scores: dict[DocumentType, int] = {}
    for doc_type, keywords in _SIGNALS.items():
        score = sum(1 for kw in keywords if kw in lowered)
        # a strong single hit for the heading counts double
        if re.search(rf"^\s*{doc_type.value.replace('_', ' ')}\b", lowered, re.M):
            score += 2
        scores[doc_type] = score

    best_type, best_score = max(scores.items(), key=lambda kv: kv[1])
    # Require at least two independent signals before committing to a type.
    # A single weak keyword hit (common in résumés, letters, random PDFs) is not
    # enough — those route to UNKNOWN so the LLM produces a summary instead of
    # being forced to extract fields for the wrong schema.
    if best_score < 2:
        return DocumentType.UNKNOWN, 0.0

    total = sum(scores.values()) or 1
    confidence = round(min(0.99, 0.4 + best_score / (total + 2)), 3)
    return best_type, confidence
