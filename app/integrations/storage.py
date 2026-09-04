"""S3-compatible object storage (MinIO locally, AWS S3 in production).

Credentials never leave the server. Clients get presigned URLs only when explicitly
requested by a route — the raw bucket is never exposed.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings
from app.core.exceptions import UpstreamError
from app.core.logging import get_logger

log = get_logger(__name__)


class ObjectStorage:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        self.bucket = settings.s3_bucket

    # --- sync internals, run in a threadpool ------------------------------
    def _ensure_bucket_sync(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self._client.create_bucket(Bucket=self.bucket)
                log.info("created storage bucket", fields={"bucket": self.bucket})
            except ClientError as exc:  # pragma: no cover - race on concurrent create
                if exc.response.get("Error", {}).get("Code") not in {
                    "BucketAlreadyOwnedByYou",
                    "BucketAlreadyExists",
                }:
                    raise

    def _put_sync(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type
        )

    def _get_sync(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def _delete_sync(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def _presign_sync(self, key: str, expires: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires,
        )

    # --- async wrappers ------------------------------------------------------
    async def _run(self, fn: Any, *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, functools.partial(fn, *args))
        except ClientError as exc:
            raise UpstreamError(f"object storage error: {exc}") from exc

    async def ensure_bucket(self) -> None:
        await self._run(self._ensure_bucket_sync)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await self._run(self._put_sync, key, data, content_type)

    async def get(self, key: str) -> bytes:
        return await self._run(self._get_sync, key)

    async def delete(self, key: str) -> None:
        await self._run(self._delete_sync, key)

    async def presigned_get_url(self, key: str, expires: int = 900) -> str:
        return await self._run(self._presign_sync, key, expires)


class InMemoryObjectStorage:
    """Dict-backed storage used by the test-suite and single-node demos
    (STORAGE_BACKEND=memory). API-compatible with :class:`ObjectStorage`."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}
        self.bucket = settings.s3_bucket

    async def ensure_bucket(self) -> None:
        return None

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        if key not in self._objects:
            raise UpstreamError(f"object not found: {key}")
        return self._objects[key][0]

    async def delete(self, key: str) -> None:
        self._objects.pop(key, None)

    async def presigned_get_url(self, key: str, expires: int = 900) -> str:
        return f"memory://{self.bucket}/{key}"


@functools.lru_cache
def get_storage():
    if settings.storage_backend.lower() == "memory":
        return InMemoryObjectStorage()
    return ObjectStorage()
