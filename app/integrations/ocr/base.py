from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class OcrResult:
    text: str
    provider: str
    char_count: int
    # Mean per-word confidence in [0, 1] when the engine reports it, else None.
    mean_confidence: float | None = None


class OCRProvider(abc.ABC):
    """Pluggable OCR backend.

    Implementations must be safe to call concurrently and must raise
    ``app.core.exceptions.UpstreamError`` on transient failures so the retry
    machinery can kick in. A future ``TextractOCRProvider`` slots in here with no
    changes to the processing pipeline.
    """

    name: str = "base"

    @abc.abstractmethod
    async def extract_text(self, content: bytes, mime_type: str, *, filename: str) -> OcrResult:
        ...
