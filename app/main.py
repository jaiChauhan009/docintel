from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.v1 import api_v1_router
from app.core.config import settings
from app.core.exceptions import DocIntelError
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.redis import close_redis
from app.integrations.events import get_event_publisher
from app.integrations.storage import get_storage

configure_logging(settings.log_level)
log = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("starting DocIntel API", fields={"env": settings.env})
    publisher = get_event_publisher()
    try:
        await publisher.start()
    except Exception as exc:  # noqa: BLE001
        log.error("event publisher failed to start", fields={"error": str(exc)})
    try:
        await get_storage().ensure_bucket()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not ensure storage bucket", fields={"error": str(exc)})
    yield
    await publisher.stop()
    await close_redis()
    log.info("DocIntel API stopped")


app = FastAPI(
    title="DocIntel API",
    version="0.1.0",
    description="AI Document Intelligence platform — upload documents, get structured data back.",
    lifespan=lifespan,
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)


@app.exception_handler(DocIntelError)
async def _domain_error_handler(request: Request, exc: DocIntelError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.code,
            "detail": exc.message,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "docintel", "docs": "/docs", "health": "/api/v1/health"}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
