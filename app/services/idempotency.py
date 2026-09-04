from __future__ import annotations

import hashlib


def request_fingerprint(*, user_id: str, filename: str, checksum: str, content_type: str) -> str:
    raw = f"{user_id}|{filename}|{checksum}|{content_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
