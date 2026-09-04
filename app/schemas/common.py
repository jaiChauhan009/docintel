from __future__ import annotations

import datetime as dt
import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    error: str
    detail: str
    request_id: str | None = None


class MessageResponse(BaseModel):
    message: str


def _dt(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


__all__ = ["ORMModel", "Page", "ErrorResponse", "MessageResponse", "uuid", "_dt"]
