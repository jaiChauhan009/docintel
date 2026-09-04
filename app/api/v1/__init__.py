from fastapi import APIRouter

from app.api.v1 import api_keys, auth, documents, health, webhooks

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth.router)
api_v1_router.include_router(documents.router)
api_v1_router.include_router(api_keys.router)
api_v1_router.include_router(webhooks.router)
api_v1_router.include_router(health.router)

__all__ = ["api_v1_router"]
