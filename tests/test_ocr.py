import pytest

from app.core.exceptions import ValidationError
from app.integrations.ocr.tesseract import PlainTextOCRProvider, TesseractOCRProvider

pytestmark = pytest.mark.asyncio


async def test_plaintext_provider_reads_text():
    ocr = PlainTextOCRProvider()
    res = await ocr.extract_text(b"Hello  world\n", "text/plain", filename="a.txt")
    assert res.text == "Hello  world"
    assert res.provider == "plaintext"
    assert res.char_count == len("Hello  world")
    assert res.mean_confidence == 1.0


async def test_plaintext_provider_rejects_binary():
    ocr = PlainTextOCRProvider()
    with pytest.raises(ValidationError):
        await ocr.extract_text(b"\x89PNG\r\n", "image/png", filename="a.png")


async def test_tesseract_provider_shortcuts_text_without_engine():
    # .txt / text/* never touches the tesseract binary
    ocr = TesseractOCRProvider()
    res = await ocr.extract_text(b"just text", "text/plain", filename="note.txt")
    assert res.text == "just text"
    assert res.provider == "tesseract"


async def test_provider_selection_from_settings(monkeypatch):
    from app.core import config
    from app.integrations.ocr.tesseract import get_ocr_provider

    monkeypatch.setattr(config.settings, "ocr_provider", "plaintext")
    assert isinstance(get_ocr_provider(), PlainTextOCRProvider)
    monkeypatch.setattr(config.settings, "ocr_provider", "tesseract")
    assert isinstance(get_ocr_provider(), TesseractOCRProvider)
