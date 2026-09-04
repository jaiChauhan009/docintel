import pytest

from app.core.exceptions import ValidationError
from app.services.extraction_parser import validate_extraction



def test_rejects_non_json():
    with pytest.raises(ValidationError):
        validate_extraction("this is not json at all", "invoice")


def test_rejects_json_array():
    with pytest.raises(ValidationError):
        validate_extraction("[1, 2, 3]", "invoice")


def test_strips_markdown_code_fences():
    raw = '```json\n{"document_type": "receipt", "total": 9.99, "confidence": 0.8}\n```'
    data, conf = validate_extraction(raw, "receipt")
    assert data["total"] == 9.99
    assert conf == 0.8


def test_extracts_object_from_surrounding_prose():
    raw = 'Sure! Here is the result: {"document_type":"receipt","confidence":0.5} hope that helps'
    data, _ = validate_extraction(raw, "receipt")
    assert data["document_type"] == "receipt"


def test_rejects_unknown_fields():
    raw = '{"document_type":"receipt","confidence":0.5,"evil_injected_field":"x"}'
    with pytest.raises(ValidationError):
        validate_extraction(raw, "receipt")


def test_rejects_wrong_types():
    raw = '{"document_type":"invoice","total":"not-a-number","confidence":0.5}'
    with pytest.raises(ValidationError):
        validate_extraction(raw, "invoice")


def test_confidence_is_clamped():
    data, conf = validate_extraction('{"document_type":"receipt","confidence":5}', "receipt")
    assert conf == 1.0
    data, conf = validate_extraction('{"document_type":"receipt","confidence":-3}', "receipt")
    assert conf == 0.0


def test_declared_type_overrides_model_claim():
    # model lies and says "receipt"; caller asked for invoice
    raw = '{"document_type":"receipt","confidence":0.9}'
    data, _ = validate_extraction(raw, "invoice")
    assert data["document_type"] == "invoice"


def test_bank_transaction_type_normalised():
    raw = (
        '{"document_type":"bank_statement","confidence":0.4,'
        '"transactions":[{"amount":10,"type":"WEIRD"}]}'
    )
    data, _ = validate_extraction(raw, "bank_statement")
    assert data["transactions"][0]["type"] == "unknown"
