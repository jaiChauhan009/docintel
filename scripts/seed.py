"""Seed the running DocIntel API with a demo user + the sample documents.

Usage:
    python scripts/seed.py                    # against http://localhost:8000
    API_BASE_URL=http://api:8000 python scripts/seed.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

import httpx

API = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.getenv("SEED_EMAIL", "demo@docintel.io")
PASSWORD = os.getenv("SEED_PASSWORD", "demo-password-123")
SAMPLES = pathlib.Path(__file__).resolve().parent.parent / "samples"


def _token(client: httpx.Client) -> str:
    r = client.post("/api/v1/auth/register",
                    json={"email": EMAIL, "password": PASSWORD, "full_name": "Demo User"})
    if r.status_code == 201:
        print(f"registered {EMAIL}")
        return r.json()["access_token"]
    r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    print(f"logged in as {EMAIL}")
    return r.json()["access_token"]


def main() -> int:
    with httpx.Client(base_url=API, timeout=30) as client:
        for _ in range(30):
            try:
                if client.get("/api/v1/health").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)

        headers = {"Authorization": f"Bearer {_token(client)}"}
        doc_ids: list[str] = []
        for sample in sorted(SAMPLES.glob("*.txt")):
            files = {"file": (sample.name, sample.read_bytes(), "text/plain")}
            r = client.post("/api/v1/documents", headers=headers, files=files)
            r.raise_for_status()
            doc_ids.append(r.json()["id"])
            print(f"uploaded {sample.name} -> {r.json()['id']} ({r.json()['status']})")

        print("\nwaiting for processing ...")
        deadline = time.time() + 120
        pending = set(doc_ids)
        while pending and time.time() < deadline:
            time.sleep(3)
            for doc_id in list(pending):
                d = client.get(f"/api/v1/documents/{doc_id}", headers=headers).json()
                if d["status"] in {"COMPLETED", "FAILED"}:
                    print(f"  {doc_id}  {d['status']}  type={d['document_type']}  conf={d['confidence']}")
                    pending.discard(doc_id)

        print("\ndone. Try:")
        print(f"  curl -s {API}/api/v1/documents -H 'Authorization: Bearer <token>' | jq")
        return 0 if not pending else 1


if __name__ == "__main__":
    sys.exit(main())
