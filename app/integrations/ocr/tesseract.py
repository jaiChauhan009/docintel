from __future__ import annotations

import asyncio
import io

from app.core.config import settings
from app.core.exceptions import UpstreamError, ValidationError
from app.core.logging import get_logger
from app.core.metrics import ocr_requests_total
from app.integrations.ocr.base import OcrResult, OCRProvider

log = get_logger(__name__)


class PlainTextOCRProvider(OCRProvider):
    """Not real OCR - reads text/* payloads verbatim.

    Used for demos and the sample documents so the whole pipeline can be exercised
    without Tesseract installed. Non-text payloads are rejected.
    """

    name = "plaintext"

    async def extract_text(self, content: bytes, mime_type: str, *, filename: str) -> OcrResult:
        if not (mime_type.startswith("text/") or filename.lower().endswith(".txt")):
            raise ValidationError("plaintext OCR provider only supports text/* documents")
        text = content.decode("utf-8", errors="replace").strip()
        ocr_requests_total.labels(provider=self.name, outcome="success").inc()
        return OcrResult(text=text, provider=self.name, char_count=len(text), mean_confidence=1.0)


class TesseractOCRProvider(OCRProvider):
    name = "tesseract"

    def __init__(self) -> None:
        self._langs = settings.ocr_languages
        self._timeout = settings.ocr_timeout_seconds

    def _run_sync(self, content: bytes, mime_type: str, filename: str) -> OcrResult:
        # text/* short-circuit: nothing to OCR.
        if mime_type.startswith("text/") or filename.lower().endswith(".txt"):
            text = content.decode("utf-8", errors="replace").strip()
            return OcrResult(text=text, provider=self.name, char_count=len(text), mean_confidence=1.0)

        import pytesseract  # imported lazily so the API process needn't have it
        from PIL import Image

        images: list = []
        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(content, fmt="png", dpi=200)
        else:
            images = [Image.open(io.BytesIO(content))]

        chunks: list[str] = []
        confidences: list[float] = []
        for image in images:
            chunks.append(pytesseract.image_to_string(image, lang=self._langs))
            data = pytesseract.image_to_data(
                image, lang=self._langs, output_type=pytesseract.Output.DICT
            )
            for conf in data.get("conf", []):
                try:
                    c = float(conf)
                except (TypeError, ValueError):
                    continue
                if c >= 0:
                    confidences.append(c / 100.0)

        text = "\n\n".join(c.strip() for c in chunks).strip()
        mean_conf = sum(confidences) / len(confidences) if confidences else None
        return OcrResult(
            text=text, provider=self.name, char_count=len(text), mean_confidence=mean_conf
        )

    async def extract_text(self, content: bytes, mime_type: str, *, filename: str) -> OcrResult:
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._run_sync, content, mime_type, filename),
                timeout=self._timeout + 5,
            )
        except asyncio.TimeoutError as exc:
            ocr_requests_total.labels(provider=self.name, outcome="timeout").inc()
            raise UpstreamError("OCR timed out") from exc
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalise to a retryable error
            ocr_requests_total.labels(provider=self.name, outcome="error").inc()
            raise UpstreamError(f"OCR failed: {exc}") from exc

        ocr_requests_total.labels(provider=self.name, outcome="success").inc()
        return result


def get_ocr_provider() -> OCRProvider:
    provider = settings.ocr_provider.lower()
    if provider == "plaintext":
        return PlainTextOCRProvider()
    return TesseractOCRProvider()
