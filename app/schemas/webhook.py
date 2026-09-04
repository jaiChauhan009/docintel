from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field, HttpUrl

from app.schemas.common import ORMModel


class WebhookCreate(BaseModel):
    url: HttpUrl
    event_types: list[str] = Field(default_factory=lambda: ["document.processed"])


class WebhookOut(ORMModel):
    id: uuid.UUID
    url: str
    event_types: list[str]
    is_active: bool
    created_at: dt.datetime


class WebhookCreated(WebhookOut):
    secret: str  # shown once


class WebhookDeliveryOut(ORMModel):
    id: uuid.UUID
    event_type: str
    status: str
    attempts: int
    last_status_code: int | None
    last_error: str | None
    delivered_at: dt.datetime | None
    created_at: dt.datetime
