"""Defensive parsing + validation of untrusted LLM output."""
from __future__ import annotations

import json
import re

from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.models.enums import DocumentType
from app.schemas.extraction import schema_for

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)


def _coerce_json(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValidationError("LLM returned an empty response")
    text = _FENCE_RE.sub("", text).strip()

    # Fast path.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the first balanced {...} block.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValidationError("LLM response is not valid JSON")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValidationError(f"LLM response is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValidationError("LLM response must be a JSON object")
    return parsed


def validate_extraction(raw: str, document_type: str | DocumentType) -> tuple[dict, float]:
    """Return ``(validated_dict, confidence)`` or raise ``ValidationError``."""
    data = _coerce_json(raw)
    # Force the declared type; never trust the model's own claim here.
    data["document_type"] = DocumentType(document_type).value
    schema = schema_for(document_type)
    try:
        model = schema.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError(f"LLM output failed schema validation: {exc.errors()}") from exc
    payload = model.model_dump(mode="json")
    return payload, float(payload.get("confidence", 0.0))
