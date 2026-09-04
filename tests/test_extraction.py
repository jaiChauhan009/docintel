import pathlib

import pytest

from app.integrations.llm.fake_client import FakeLLMClient
from app.integrations.llm.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models.enums import DocumentType
from app.services.classification import classify
from app.services.extraction_parser import validate_extraction

SAMPLES = pathlib.Path(__file__).parent.parent / "samples"


def _text(name: str) -> str:
    return (SAMPLES / name).read_text()


@pytest.mark.parametrize(
    "sample,expected",
    [
        ("invoice_sample.txt", DocumentType.INVOICE),
        ("receipt_sample.txt", DocumentType.RECEIPT),
        ("bank_statement_sample.txt", DocumentType.BANK_STATEMENT),
        ("contract_sample.txt", DocumentType.CONTRACT),
    ],
)
def test_classifier_identifies_sample(sample, expected):
    doc_type, conf = classify(_text(sample))
    assert doc_type == expected
    assert conf > 0


def test_classifier_unknown_on_noise():
    doc_type, conf = classify("lorem ipsum dolor sit amet")
    assert doc_type == DocumentType.UNKNOWN
    assert conf == 0.0


@pytest.mark.parametrize(
    "sample,dtype",
    [
        ("invoice_sample.txt", "invoice"),
        ("receipt_sample.txt", "receipt"),
        ("bank_statement_sample.txt", "bank_statement"),
        ("contract_sample.txt", "contract"),
    ],
)
async def test_fake_llm_output_validates_against_schema(sample, dtype):
    llm = FakeLLMClient()
    resp = await llm.complete_json(SYSTEM_PROMPT, build_user_prompt(dtype, _text(sample)))
    data, confidence = validate_extraction(resp.content, dtype)
    assert data["document_type"] == dtype
    assert 0.0 <= confidence <= 1.0


async def test_invoice_extraction_pulls_key_fields():
    llm = FakeLLMClient()
    resp = await llm.complete_json(
        SYSTEM_PROMPT, build_user_prompt("invoice", _text("invoice_sample.txt"))
    )
    data, _ = validate_extraction(resp.content, "invoice")
    assert data["vendor_name"] == "Northwind Traders LLC"
    assert data["invoice_number"] == "INV-2026-000481"
    assert data["total"] == 3924.0
    assert len(data["line_items"]) == 3
    assert data["line_items"][0]["amount"] == 2400.0


async def test_bank_statement_masks_account_number():
    llm = FakeLLMClient()
    resp = await llm.complete_json(
        SYSTEM_PROMPT, build_user_prompt("bank_statement", _text("bank_statement_sample.txt"))
    )
    data, _ = validate_extraction(resp.content, "bank_statement")
    assert data["account_number_masked"] == "****6789"
    assert "000123456789" not in str(data)
    assert len(data["transactions"]) == 8
    assert data["transactions"][0]["type"] == "credit"
    assert data["transactions"][1]["type"] == "debit"
