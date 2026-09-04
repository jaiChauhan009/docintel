from app.integrations.ocr.base import OcrResult, OCRProvider
from app.integrations.ocr.tesseract import (
    PlainTextOCRProvider,
    TesseractOCRProvider,
    get_ocr_provider,
)

__all__ = [
    "OcrResult",
    "OCRProvider",
    "PlainTextOCRProvider",
    "TesseractOCRProvider",
    "get_ocr_provider",
]
