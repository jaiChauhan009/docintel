from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import bind_context, clear_context, get_logger

log = get_logger("app.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        clear_context()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        bind_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            log.exception("request failed", fields={"duration_ms": duration_ms})
            raise
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        log.info(
            "request completed",
            fields={
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "user_id": getattr(request.state, "user_id", None),
                "auth_method": getattr(request.state, "auth_method", None),
            },
        )
        clear_context()
        return response
