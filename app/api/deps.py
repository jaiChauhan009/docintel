from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import decode_access_token, hash_api_key
from app.db.session import get_session
from app.models import User
from app.repositories.api_key_repo import ApiKeyRepository
from app.repositories.user_repo import UserRepository

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


RequestIdDep = Annotated[str, Depends(get_request_id)]


async def get_current_user(
    request: Request,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> User:
    """Authenticate via ``Authorization: Bearer <jwt>`` or ``X-API-Key: <raw key>``."""
    user: User | None = None
    auth_method = "jwt"

    if x_api_key:
        auth_method = "api_key"
        repo = ApiKeyRepository(session)
        api_key = await repo.get_by_hash(hash_api_key(x_api_key))
        if api_key is None or not api_key.is_active:
            raise AuthenticationError("invalid or revoked API key")
        api_key.last_used_at = dt.datetime.now(dt.timezone.utc)
        user = await UserRepository(session).get(api_key.user_id)
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_access_token(token)
        try:
            user_id = uuid.UUID(payload["sub"])
        except (KeyError, ValueError) as exc:
            raise AuthenticationError("malformed token subject") from exc
        user = await UserRepository(session).get(user_id)
    else:
        raise AuthenticationError("missing credentials (Bearer token or X-API-Key)")

    if user is None or not user.is_active:
        raise AuthenticationError("user not found or inactive")

    request.state.user_id = str(user.id)
    request.state.auth_method = auth_method
    await enforce_rate_limit(f"{auth_method}:{user.id}")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
