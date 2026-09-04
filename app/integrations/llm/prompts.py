"""Prompt construction for structured extraction.

The schema JSON handed to the model is generated from the Pydantic models so the
prompt and the validator can never drift apart.
"""
from __future__ import annotations

import json

from app.models.enums import DocumentType
from app.schemas.extraction import schema_for

SYSTEM_PROMPT = (
    "You are a precise document-information-extraction engine. "
    "You are given raw OCR text from a business document. "
    "Extract the requested fields and respond with a SINGLE JSON object and nothing else. "
    "No markdown, no code fences, no commentary. "
    "Use null for any field you cannot determine. Do not invent values. "
    "All monetary amounts must be plain numbers (no currency symbols, no thousands separators). "
    "Dates must be ISO-8601 (YYYY-MM-DD) when possible, otherwise copy the text as-is. "
    "'confidence' is your overall confidence in the extraction, a float between 0 and 1."
)

MAX_OCR_CHARS = 12_000


def build_user_prompt(document_type: str | DocumentType, ocr_text: str) -> str:
    schema = schema_for(document_type)
    schema_json = json.dumps(schema.model_json_schema(), indent=2)
    text = ocr_text.strip()
    if len(text) > MAX_OCR_CHARS:
        text = text[:MAX_OCR_CHARS] + "\n...[truncated]..."
    return (
        f"Document type: {DocumentType(document_type).value}\n\n"
        f"Return JSON that conforms to this JSON Schema:\n{schema_json}\n\n"
        f"--- BEGIN OCR TEXT ---\n{text}\n--- END OCR TEXT ---"
    )
