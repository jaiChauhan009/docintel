"""Prometheus metrics. Import and increment from anywhere; exposed at GET /metrics."""
from __future__ import annotations

from prometheus_client import Counter, Histogram

documents_uploaded_total = Counter(
    "documents_uploaded_total", "Documents accepted for processing", ["document_hint"]
)
documents_processed_total = Counter(
    "documents_processed_total", "Documents that reached COMPLETED", ["document_type"]
)
documents_failed_total = Counter(
    "documents_failed_total", "Documents that reached FAILED", ["reason"]
)
processing_duration_seconds = Histogram(
    "processing_duration_seconds",
    "Wall-clock duration of a single processing attempt",
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300),
)
llm_requests_total = Counter(
    "llm_requests_total", "LLM extraction calls", ["provider", "outcome"]
)
ocr_requests_total = Counter(
    "ocr_requests_total", "OCR calls", ["provider", "outcome"]
)
webhook_deliveries_total = Counter(
    "webhook_deliveries_total", "Webhook delivery attempts", ["outcome"]
)
