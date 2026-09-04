"""Redis fixed-window rate limiter + a tiny JSON cache helper.

Fails open: if Redis is unavailable the request is allowed (availability > strictness
for an MVP), but the failure is logged.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import settings
from app.core.exceptions import RateLimitedError
from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)


async def enforce_rate_limit(identity: str) -> None:
    limit = settings.rate_limit_requests
    window = settings.rate_limit_window_seconds
    bucket = int(time.time() // window)
    key = f"rl:{identity}:{bucket}"
    try:
        redis = get_redis()
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window)
    except Exception as exc:  # noqa: BLE001
        log.warning("rate limiter unavailable, allowing request", fields={"error": str(exc)})
        return
    if current > limit:
        raise RateLimitedError(f"rate limit exceeded ({limit}/{window}s)")


async def cache_get_json(key: str) -> Any | None:
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache get failed", fields={"error": str(exc)})
        return None
    return json.loads(raw) if raw else None


async def cache_set_json(key: str, value: Any, ttl: int = 60) -> None:
    try:
        await get_redis().set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache set failed", fields={"error": str(exc)})


async def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        await get_redis().delete(*keys)
    except Exception as exc:  # noqa: BLE001
        log.warning("cache delete failed", fields={"error": str(exc)})
