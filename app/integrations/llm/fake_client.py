"""Deterministic, offline stand-in for a real LLM.

It performs lightweight regex extraction over the OCR text and emits JSON that
conforms to the target schema. This keeps the whole pipeline exercisable in
docker-compose and CI with no API key and no cost. Select it with LLM_PROVIDER=fake.
"""
from __future__ import annotations

import json
import re

from app.core.metrics import llm_requests_total
from app.integrations.llm.base import LLMClient, LLMResponse
from app.models.enums import DocumentType

_MONEY = r"[-+]?\$?\s?([0-9][0-9,]*\.?[0-9]{0,2})"
_DATE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z][a-z]+ \d{1,2},? \d{4})"


def _num(text: str, *labels: str) -> float | None:
    for label in labels:
        # label, optional colon/whitespace, then the number -- avoids matching
        # things like "Tax ID: 91-..." for the label "tax".
        m = re.search(rf"{label}\b[ \t]*:?[ \t]*{_MONEY}", text, re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _str(text: str, *labels: str) -> str | None:
    for label in labels:
        m = re.search(rf"{label}\s*[:#]?\s*(.+)", text, re.I)
        if m:
            val = m.group(1).strip().splitlines()[0].strip(" .:-")
            if val:
                return val
    return None


def _date(text: str, *labels: str) -> str | None:
    for label in labels:
        m = re.search(rf"{label}[^0-9A-Za-z]*{_DATE}", text, re.I)
        if m:
            return m.group(1).strip()
    return None


def _extract_invoice(text: str) -> dict:
    items: list[dict] = []
    for line in text.splitlines():
        m = re.match(
            rf"\s*(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+{_MONEY}\s+{_MONEY}\s*$", line
        )
        if m:
            items.append(
                {
                    "description": m.group("desc").strip(),
                    "quantity": float(m.group("qty")),
                    "unit_price": float(m.group(3).replace(",", "")),
                    "amount": float(m.group(4).replace(",", "")),
                }
            )
    return {
        "document_type": "invoice",
        "vendor_name": _str(text, "vendor", "from", "bill from", "seller"),
        "invoice_number": _str(text, "invoice number", "invoice no", "invoice #", "invoice"),
        "invoice_date": _date(text, "invoice date", "date of issue", "date"),
        "due_date": _date(text, "due date", "payment due"),
        "currency": (_str(text, "currency") or ("USD" if "$" in text else None)),
        "subtotal": _num(text, "subtotal", "sub total"),
        "tax": _num(text, "tax", "vat", "gst"),
        "total": _num(text, "total due", "grand total", "amount due", "total"),
        "line_items": items,
        "confidence": 0.72 if items else 0.55,
    }


def _extract_receipt(text: str) -> dict:
    return {
        "document_type": "receipt",
        "merchant_name": _str(text, "merchant", "store", "restaurant") or text.strip().splitlines()[0][:80],
        "transaction_date": _date(text, "date", "transaction date"),
        "currency": "USD" if "$" in text else _str(text, "currency"),
        "subtotal": _num(text, "subtotal", "sub total"),
        "tax": _num(text, "tax", "vat", "gst"),
        "total": _num(text, "total", "amount", "balance due"),
        "payment_method": _str(text, "payment method", "paid with", "card", "tender"),
        "confidence": 0.68,
    }


def _extract_bank_statement(text: str) -> dict:
    txns: list[dict] = []
    for line in text.splitlines():
        m = re.match(rf"\s*{_DATE}\s+(?P<desc>.+?)\s+(?P<sign>[-+]?){_MONEY}\s*$", line)
        if m:
            amount = float(m.group(4).replace(",", ""))
            sign = m.group("sign")
            txns.append(
                {
                    "date": m.group(1),
                    "description": m.group("desc").strip(),
                    "amount": amount,
                    "type": "debit" if sign == "-" else "credit",
                }
            )
    acct = _str(text, "account number", "account no", "acct")
    if acct:
        digits = "".join(c for c in acct if c.isdigit())
        acct = "****" + digits[-4:] if len(digits) > 4 else acct
    return {
        "document_type": "bank_statement",
        "account_holder": _str(text, "account holder", "name"),
        "account_number_masked": acct,
        "bank_name": _str(text, "bank", "issued by") or text.strip().splitlines()[0][:80],
        "statement_period_start": _date(text, "statement period", "period from", "from"),
        "statement_period_end": _date(text, "to", "period to", "ending"),
        "opening_balance": _num(text, "opening balance", "beginning balance"),
        "closing_balance": _num(text, "closing balance", "ending balance"),
        "transactions": txns,
        "confidence": 0.7 if txns else 0.5,
    }


def _extract_contract(text: str) -> dict:
    parties = []
    for m in re.finditer(r'"([^"]+)"\s*\(the\s+"?([^")]+)"?\)', text):
        parties.append({"name": m.group(1).strip(), "role": m.group(2).strip()})
    if not parties:
        for m in re.finditer(r"between\s+(.+?)\s+and\s+(.+?)[\.\n]", text, re.I):
            parties = [{"name": m.group(1).strip(), "role": None},
                       {"name": m.group(2).strip(), "role": None}]
            break
    return {
        "document_type": "contract",
        "parties": parties,
        "effective_date": _date(text, "effective date", "commencement date", "dated"),
        "expiration_date": _date(text, "expiration date", "termination date", "expires", "end date"),
        "contract_value": _num(text, "contract value", "total value", "consideration", "fee"),
        "currency": "USD" if "$" in text else None,
        "obligations": [
            ln.strip(" -*\t") for ln in text.splitlines()
            if re.search(r"\bshall\b|\bmust\b|\bagrees to\b", ln, re.I)
        ][:10],
        "important_dates": re.findall(_DATE, text)[:10],
        "termination_clauses": [
            ln.strip() for ln in re.split(r"(?<=[.\n])", text)
            if "terminat" in ln.lower()
        ][:5],
        "confidence": 0.6 if parties else 0.4,
    }


_EXTRACTORS = {
    DocumentType.INVOICE: _extract_invoice,
    DocumentType.RECEIPT: _extract_receipt,
    DocumentType.BANK_STATEMENT: _extract_bank_statement,
    DocumentType.CONTRACT: _extract_contract,
}


class FakeLLMClient(LLMClient):
    provider = "fake"
    model = "deterministic-regex-v1"

    async def complete_json(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        # The user prompt embeds "Document type: X" and the OCR block.
        m = re.search(r"Document type:\s*(\w+)", user_prompt)
        doc_type = DocumentType(m.group(1)) if m else DocumentType.UNKNOWN
        ocr = user_prompt.split("--- BEGIN OCR TEXT ---", 1)[-1]
        ocr = ocr.split("--- END OCR TEXT ---", 1)[0]

        extractor = _EXTRACTORS.get(doc_type)
        data = extractor(ocr) if extractor else {
            "document_type": "unknown",
            "summary": ocr.strip()[:200] or None,
            "confidence": 0.3,
        }
        llm_requests_total.labels(provider=self.provider, outcome="success").inc()
        return LLMResponse(content=json.dumps(data), provider=self.provider, model=self.model)
