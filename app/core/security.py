"""Password hashing, JWT issue/verify, and API-key hashing helpers."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
import uuid

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AuthenticationError

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

API_KEY_PREFIX = "dik_"  # DocIntel key


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except ValueError:
        return False


def create_access_token(subject: str, extra: dict | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_access_token_ttl_minutes),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("invalid token") from exc
    if payload.get("type") != "access":
        raise AuthenticationError("wrong token type")
    return payload


# --- API keys -------------------------------------------------------------
# We never persist the raw key. We store sha256(key) and show the raw value once.

def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, key_hash, key_prefix). ``key_prefix`` is safe to display."""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw), raw[:12]


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def api_key_matches(raw: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw), stored_hash)
