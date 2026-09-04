"""Structured JSON logging + a request/processing context that is attached to every log line."""
from __future__ import annotations

import contextvars
import datetime as dt
import json
import logging
import sys
from typing import Any

_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("log_context", default={})

# Fields that must never be written to logs verbatim.
_SENSITIVE_KEYS = {
    "password",
    "hashed_password",
    "authorization",
    "token",
    "access_token",
    "api_key",
    "raw_key",
    "secret",
    "ocr_text",
    "extracted_data",
    "document_text",
}


def bind_context(**kwargs: Any) -> None:
    data = dict(_context.get())
    data.update({k: v for k, v in kwargs.items() if v is not None})
    _context.set(data)


def clear_context() -> None:
    _context.set({})


def get_context() -> dict[str, Any]:
    return dict(_context.get())


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("***" if k.lower() in _SENSITIVE_KEYS else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_scrub(get_context()))

        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(_scrub(extra))

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class ContextLogger(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        extra = kwargs.pop("extra", {}) or {}
        fields = kwargs.pop("fields", {}) or {}
        merged = {**extra, "extra_fields": fields}
        kwargs["extra"] = merged
        return msg, kwargs


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Quiet down noisy third-party loggers.
    for noisy in ("aiokafka", "botocore", "boto3", "uvicorn.access"):
        logging.getLogger(noisy).setLevel("WARNING")


def get_logger(name: str) -> ContextLogger:
    return ContextLogger(logging.getLogger(name), {})
