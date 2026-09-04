from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, RequestIdDep, SessionDep
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: SessionDep, request_id: RequestIdDep):
    service = AuthService(session)
    user = await service.register(
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        request_id=request_id,
    )
    return service.issue_token(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep):
    service = AuthService(session)
    user = await service.authenticate(email=payload.email, password=payload.password)
    return service.issue_token(user)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
