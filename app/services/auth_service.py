from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories.audit_repo import AuditLogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import TokenResponse


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditLogRepository(session)

    async def register(
        self, *, email: str, password: str, full_name: str | None, request_id: str | None = None
    ) -> User:
        if await self.users.get_by_email(email):
            raise ConflictError("a user with that email already exists")
        user = await self.users.create(
            email=email, hashed_password=hash_password(password), full_name=full_name
        )
        await self.audit.record(
            action="user.register",
            resource_type="user",
            resource_id=str(user.id),
            user_id=user.id,
            request_id=request_id,
            detail={"email_domain": email.split("@")[-1]},
        )
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("invalid email or password")
        if not user.is_active:
            raise AuthenticationError("account is disabled")
        return user

    def issue_token(self, user: User) -> TokenResponse:
        token = create_access_token(str(user.id), extra={"email": user.email})
        return TokenResponse(
            access_token=token,
            expires_in=settings.jwt_access_token_ttl_minutes * 60,
        )
