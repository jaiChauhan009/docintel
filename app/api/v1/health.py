from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: SessionDep):
    checks: dict[str, str] = {}

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    healthy = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "env": settings.env,
        "checks": checks,
        "config": {
            "ocr_provider": settings.ocr_provider,
            "llm_provider": settings.llm_provider,
            "event_bus": settings.event_bus,
            "max_processing_attempts": settings.max_processing_attempts,
        },
    }
