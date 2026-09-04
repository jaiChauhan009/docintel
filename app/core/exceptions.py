"""Domain exceptions. The API layer maps these onto HTTP responses."""
from __future__ import annotations


class DocIntelError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.__doc__ or self.code)
        self.message = message or self.code


class NotFoundError(DocIntelError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(DocIntelError):
    status_code = 403
    code = "permission_denied"


class AuthenticationError(DocIntelError):
    status_code = 401
    code = "authentication_failed"


class ValidationError(DocIntelError):
    status_code = 422
    code = "validation_error"


class ConflictError(DocIntelError):
    status_code = 409
    code = "conflict"


class RateLimitedError(DocIntelError):
    status_code = 429
    code = "rate_limited"


class UpstreamError(DocIntelError):
    """Raised when OCR/LLM/storage calls fail; these are retryable."""

    status_code = 502
    code = "upstream_error"
