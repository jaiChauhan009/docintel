from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ApiKeyOut(ORMModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None


class ApiKeyCreated(ApiKeyOut):
    # Present only in the create response, never again.
    api_key: str
