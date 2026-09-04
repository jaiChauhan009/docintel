# DocIntel — AI Document Intelligence Platform

Upload invoices, receipts, contracts and bank statements. DocIntel stores the
original file, processes it asynchronously (OCR → classification → LLM extraction →
schema validation), persists structured data, and exposes APIs to poll status and
fetch results. JWT + API-key auth, webhooks, idempotent uploads, retries with
backoff, structured JSON logs and Prometheus metrics are all included.

The whole stack runs locally with one command and **needs no paid API keys** —
OCR uses Tesseract and the LLM defaults to a deterministic offline stub.

```bash
cp .env.example .env
docker compose up --build
# API      -> http://localhost:8000        (Swagger UI at /docs)
# Frontend -> http://localhost:5173
# MinIO    -> http://localhost:9001        (minioadmin / minioadmin)
python scripts/seed.py                     # uploads the sample documents
```

---

## 1. Architecture

```
                         ┌──────────────────┐
                         │  React dashboard │  (Vite + TS)
                         └────────┬─────────┘
                                  │ HTTPS / JSON
                        ┌─────────▼──────────┐         ┌───────────────┐
   Idempotency-Key ────▶│    FastAPI API     │────────▶│  PostgreSQL   │  users, documents,
   JWT / X-API-Key      │  (controllers →    │◀────────│  (SQLAlchemy  │  document_results,
                        │  services →        │         │   2.x async)  │  processing_attempts,
                        │  repositories)     │         └───────────────┘  audit_logs, api_keys,
                        └───┬─────────┬──────┘                            webhooks, idempotency_keys
                            │         │
             put/get object │         │ publish "document.processing"
                            ▼         ▼
                     ┌────────────┐  ┌──────────┐
                     │  MinIO/S3  │  │  Kafka   │
                     └────────────┘  └────┬─────┘
                            ▲             │ consume (group: docintel-workers)
                            │             ▼
                            │      ┌──────────────────────────────────────┐
                            │      │        Worker (Kafka consumer)       │
                            └──────┤  download → OCR (Tesseract) →        │
                                   │  classify → LLM extract →            │
                     ┌─────────────┤  Pydantic validate → persist →      │
                     │   Redis     │  emit webhook  (retry w/ backoff)   │
                     │ rate-limit  │  retry loop for webhook deliveries  │
                     │  + cache    │  metrics on :9100                   │
                     └─────────────┘  └──────────────────────────────────┘
```

**Clean architecture layering** (`app/`):

| layer | responsibility | never does |
|---|---|---|
| `api/` | HTTP shape, auth deps, status codes | business logic |
| `services/` | orchestration, transitions, validation | raw SQL, HTTP framing |
| `repositories/` | data access (SQLAlchemy) | business rules |
| `integrations/` | storage, OCR, LLM, Kafka — each behind an interface | knowing about HTTP or the DB |
| `models/` `schemas/` | ORM tables / Pydantic contracts | — |

Swapping Tesseract for AWS Textract = one new class implementing
`integrations/ocr/base.OCRProvider`; nothing else changes.

---

## 2. Why Kafka

* **Decouples upload from processing.** The API returns `202 UPLOADED` in
  milliseconds; heavy OCR/LLM work happens off the request path.
* **Durable, replayable buffer.** If every worker is down, events wait on the
  topic; workers resume from their committed offset — nothing is lost.
* **Horizontal scale.** Add worker replicas in the same consumer group and Kafka
  partitions the load. The document id is the partition key, so all events for one
  document stay ordered.
* **At-least-once + idempotent processing.** Offsets are committed only after a
  batch is handled; the processor treats already-`COMPLETED`/`PROCESSING`
  documents as no-ops, so redelivery is safe.

An in-memory bus (`integrations/events/memory_bus.py`) implements the same
interface for tests and single-process demos (`EVENT_BUS=fake`).

---

## 3. Why Redis

* **API rate limiting** — fixed-window counter per `user`/`api_key`
  (`RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS`). Fails **open** if Redis
  is unreachable so availability isn't coupled to it.
* **Read caching** — short-TTL JSON cache helper for hot document reads.
* **Fast idempotency pre-check** — a Redis lookup short-circuits before hitting
  Postgres (the DB unique constraint remains the source of truth).

---

## 4. Database schema

UUID primary keys everywhere. Timestamps (`created_at`, `updated_at`) on every
table. Migrations live in `alembic/versions/` (`alembic upgrade head`, run
automatically by the API container entrypoint).

| table | purpose | key columns / indexes |
|---|---|---|
| `users` | accounts | `email` unique |
| `documents` | one row per upload | `user_id`, `status`, `document_type`, `storage_key`, `checksum_sha256`, `retry_count`, `idempotency_key`; composite indexes `(user_id,status)`, `(user_id,created_at)` |
| `document_results` | validated extraction | `document_id` unique (1:1), `extracted_data` (JSON), `masked_data` (JSON), `confidence`, provider/model metadata |
| `processing_attempts` | audit of every attempt | `document_id`, `attempt_number`, `status`, `stage`, `error_type`, `error_message`, `duration_ms` |
| `audit_logs` | security-relevant actions | `action`, `resource_type`, `resource_id`, `request_id`; **non-sensitive metadata only** |
| `api_keys` | per-user keys | `key_hash` (sha256) unique, `key_prefix` for display, `revoked_at` |
| `webhooks` | registered endpoints | `url`, `secret` (HMAC), `event_types` |
| `webhook_deliveries` | delivery attempts + retry schedule | `status`, `attempts`, `next_retry_at`, `last_status_code` |
| `idempotency_keys` | `(user_id, key)` → `document_id` | unique `(user_id, key)`, plus `request_fingerprint` |

Models use generic SQLAlchemy types (`Uuid`, `JSON`) so the identical schema runs
on Postgres (prod) and SQLite (test-suite). `alembic check` in CI guarantees the
migration and the models never drift.

---

## 5. Document processing lifecycle

```
POST /api/v1/documents
  ├─ validate MIME type + size, compute sha256
  ├─ (Idempotency-Key?) return existing document if replay
  ├─ PUT object → MinIO/S3
  ├─ INSERT documents (status = UPLOADED)
  ├─ INSERT idempotency_keys
  ├─ COMMIT, then publish {document.uploaded} → Kafka
  └─ 202 { id, status: UPLOADED }

worker consumes event
  ├─ load document; skip if COMPLETED/PROCESSING (idempotent)
  ├─ transition UPLOADED → PROCESSING   (guarded by ALLOWED_STATUS_TRANSITIONS)
  ├─ INSERT processing_attempts (started)
  ├─ stage=download : GET object from storage
  ├─ stage=ocr      : Tesseract → text (+ mean word confidence)
  ├─ stage=classify : keyword scorer → invoice|receipt|contract|bank_statement|unknown
  ├─ stage=llm      : OCR text → LLM, strict-JSON response_format
  ├─ stage=validate : parse untrusted JSON → Pydantic schema for the detected type
  ├─ stage=persist  : UPSERT document_results (+ masked copy)
  ├─ transition PROCESSING → COMPLETED, set confidence
  ├─ mark attempt succeeded, observe processing_duration_seconds
  └─ enqueue webhook  document.processed

on any stage error → see §7
```

**States:** `UPLOADED → PROCESSING → COMPLETED` or `→ FAILED`.
`FAILED` documents can be re-driven with `POST /api/v1/documents/{id}/retry`.

---

## 6. AI extraction strategy

1. **Classify first, cheaply.** A keyword scorer picks the document type before
   spending an LLM call, so the model gets a targeted schema.
2. **Schema-locked prompt.** The system prompt forbids prose/markdown; the user
   prompt embeds the exact JSON Schema generated *from the Pydantic model*
   (`schemas/extraction.py`) — prompt and validator cannot drift. OpenAI path also
   sets `response_format={"type":"json_object"}` and `temperature=0`.
3. **Treat LLM output as untrusted input** (`services/extraction_parser.py`):
   * strip code fences, then `json.loads`; on failure, extract the first balanced
     `{...}` block; reject arrays / non-objects.
   * `extra="forbid"` on every schema → a hallucinated field fails validation
     rather than leaking through.
   * `document_type` is overwritten with the *detected* type — the model's own
     claim is never trusted.
   * `confidence` clamped to `[0,1]`; bank `type` normalised to
     `credit|debit|unknown`; account numbers force-masked to `****1234`.
4. **Timeouts** on both OCR and LLM calls; failures become retryable
   `UpstreamError`s.
5. **Providers are pluggable.** `LLM_PROVIDER=fake` (default) is a deterministic
   regex extractor — zero cost, used in CI and demos. `LLM_PROVIDER=openai` +
   `LLM_BASE_URL` targets any OpenAI-compatible endpoint.

Confidence stored on the result is `min(llm_confidence, ocr_mean_confidence)`.

---

## 7. Retry strategy

* Max **3** attempts per document (`MAX_PROCESSING_ATTEMPTS`).
* **Retryable:** `UpstreamError` (OCR/LLM/storage/network/timeout) and unexpected
  exceptions. **Not retryable:** `ValidationError` (bad OCR text, malformed/invalid
  LLM JSON) — retrying won't help, so it fails fast.
* On a retryable failure: record the attempt, set the document back to `UPLOADED`,
  wait `RETRY_BACKOFF_BASE_SECONDS ** attempt_number` seconds, and re-publish a
  `document.retry` event.
* After the 3rd failure (or any non-retryable error): `status = FAILED`,
  `error_message` set, `documents_failed_total` incremented, webhook emitted.
* **Every** attempt — success or failure — is a row in `processing_attempts`
  (`stage`, `error_type`, `error_message`, `duration_ms`).

**Webhook retries** are independent: up to `WEBHOOK_MAX_ATTEMPTS` (default 5) with
`WEBHOOK_BACKOFF_BASE_SECONDS ** attempt` backoff. Pending deliveries carry a
`next_retry_at`; the worker's retry loop flushes due ones every few seconds.

---

## 8. Idempotency strategy

Send `Idempotency-Key: <uuid>` with `POST /api/v1/documents`.

* Key is scoped per user. A `request_fingerprint = sha256(user|filename|
  file_sha256|content_type)` is stored alongside it.
* Same key **+ same fingerprint** → the original document is returned,
  `idempotent_replay: true`, **no new object, no new Kafka event**.
* Same key **+ different body** → `409 conflict`.
* Enforced by a `UNIQUE (user_id, key)` constraint (source of truth); a Redis
  lookup is the fast path. A concurrent double-submit that loses the race catches
  the `IntegrityError` and returns the winner's document.

At-least-once Kafka delivery is made idempotent downstream: the processor no-ops
on documents already `PROCESSING`/`COMPLETED`.

---

## 9. Security considerations

* **JWT** (HS256, configurable TTL) for interactive users; **API keys** for
  machine clients via `X-API-Key`.
* **Passwords** hashed with bcrypt (passlib). **API keys** stored as sha256 only —
  the raw key is shown exactly once, on creation; keys can be revoked.
* **Ownership checks** on every document route; cross-tenant access returns `404`
  (not `403`) so existence isn't leaked.
* **Upload guards:** MIME allow-list (`ALLOWED_MIME_TYPES`), size cap
  (`MAX_UPLOAD_SIZE_MB`), empty-file rejection.
* **Rate limiting** per identity via Redis.
* **Secrets** only ever in env vars; MinIO/S3 credentials never reach a client —
  files are served (when needed) via short-lived presigned URLs generated
  server-side.
* **No sensitive content in logs.** The JSON logger scrubs keys like `password`,
  `authorization`, `token`, `api_key`, `ocr_text`, `extracted_data`. Audit logs
  store metadata only (e.g. email *domain*, file size), never document text.
* **Field masking:** bank account numbers are reduced to `****1234` both in the
  schema validator and in the separate `masked_data` copy.
* **LLM output is untrusted** — see §6.
* Webhook payloads are signed: `X-DocIntel-Signature: sha256=<hmac(secret, body)>`.

---

## 10. Local setup

### With Docker (recommended)

```bash
cp .env.example .env
docker compose up --build          # api, worker, postgres, redis, kafka (KRaft), minio, frontend
docker compose exec api alembic current
python scripts/seed.py             # register demo user + upload samples/*.txt
```

Services: API `:8000` (`/docs`, `/metrics`), worker metrics `:9100`, frontend
`:5173`, Postgres `:5432`, Redis `:6379`, Kafka `:29092` (external listener),
MinIO `:9000` / console `:9001`.

To use a real model: set `LLM_PROVIDER=openai`, `LLM_API_KEY`, `LLM_BASE_URL`,
`LLM_MODEL` in `.env` and restart.

### Without Docker (dev loop)

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
# point DATABASE_URL at a local postgres, then:
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m app.workers.consumer      # separate shell
```

### Tests

```bash
.venv/bin/python -m pytest        # 60 tests, SQLite + in-memory bus, no infra needed
```

Covers: auth, upload, ownership, status transitions, OCR service, AI extraction,
schema validation, retry logic (transient/persistent/non-retryable),
webhook retry + backoff, idempotency, API-key auth.

---

## 11. API examples

```bash
BASE=http://localhost:8000

# register (returns a JWT) / login
TOKEN=$(curl -s $BASE/api/v1/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"me@example.com","password":"supersecret1"}' | jq -r .access_token)

# upload (idempotent)
curl -s -X POST $BASE/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Idempotency-Key: $(uuidgen)" \
  -F "file=@samples/invoice_sample.txt;type=text/plain"
# -> {"id":"...","status":"UPLOADED","idempotent_replay":false}

# poll status  /  fetch result
curl -s $BASE/api/v1/documents/$ID           -H "Authorization: Bearer $TOKEN" | jq
curl -s $BASE/api/v1/documents/$ID/result    -H "Authorization: Bearer $TOKEN" | jq
curl -s $BASE/api/v1/documents               -H "Authorization: Bearer $TOKEN" | jq
curl -s -X POST $BASE/api/v1/documents/$ID/retry  -H "Authorization: Bearer $TOKEN"
curl -s -X DELETE $BASE/api/v1/documents/$ID      -H "Authorization: Bearer $TOKEN" -i

# API keys
curl -s -X POST $BASE/api/v1/api-keys -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"name":"ci"}' | jq
curl -s $BASE/api/v1/documents -H "X-API-Key: dik_xxxxxxxx..."

# webhooks
curl -s -X POST $BASE/api/v1/webhooks -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/hook","event_types":["document.processed"]}'

curl -s $BASE/api/v1/health
```

Full interactive spec: **`http://localhost:8000/docs`** (OpenAPI at `/openapi.json`).

### Endpoints

```
POST   /api/v1/auth/register        POST   /api/v1/documents
POST   /api/v1/auth/login           GET    /api/v1/documents
GET    /api/v1/auth/me              GET    /api/v1/documents/{id}
                                    GET    /api/v1/documents/{id}/result
POST   /api/v1/api-keys             POST   /api/v1/documents/{id}/retry
GET    /api/v1/api-keys             DELETE /api/v1/documents/{id}
DELETE /api/v1/api-keys/{id}
                                    GET    /api/v1/health
POST   /api/v1/webhooks             GET    /metrics        (Prometheus)
GET    /api/v1/webhooks
DELETE /api/v1/webhooks/{id}
```

---

## 12. Example extracted invoice JSON

`GET /api/v1/documents/{id}/result` for `samples/invoice_sample.txt`:

```json
{
  "document_id": "89986887-59d5-4d4e-81e9-eef3d71cebc2",
  "status": "COMPLETED",
  "document_type": "invoice",
  "confidence": 0.72,
  "extracted_data": {
    "document_type": "invoice",
    "vendor_name": "Northwind Traders LLC",
    "invoice_number": "INV-2026-000481",
    "invoice_date": "2026-08-14",
    "due_date": "2026-09-13",
    "currency": "USD",
    "subtotal": 3600.0,
    "tax": 324.0,
    "total": 3924.0,
    "line_items": [
      {"description": "Enterprise Widget (annual)", "quantity": 2.0, "unit_price": 1200.0, "amount": 2400.0},
      {"description": "Onboarding & Training",      "quantity": 1.0, "unit_price": 750.0,  "amount": 750.0},
      {"description": "Priority Support Add-on",    "quantity": 3.0, "unit_price": 150.0,  "amount": 450.0}
    ],
    "confidence": 0.72
  },
  "masked_data": { "... same shape, sensitive fields redacted ..." },
  "error_message": null
}
```

Webhook body delivered on completion:

```json
{ "event": "document.processed", "document_id": "89986887-…", "status": "completed" }
```

---

## 13. Future improvements

* **AWS Textract** provider (interface already in place); layout-aware parsing for
  tables instead of the line-regex fallback.
* **Delayed-retry topic** instead of `await asyncio.sleep()` before re-publish, so
  a worker never blocks on backoff; or a scheduled `retry_at` table + poller.
* **Dead-letter topic** for poison messages; alerting on `documents_failed_total`.
* **Prometheus multiprocess mode** / push-gateway so API + worker metrics share a
  registry (today the worker exposes its own on `:9100`).
* **Outbox pattern** for the Kafka publish so it's atomic with the DB write
  (currently: commit, then publish, with idempotent reprocessing as the backstop).
* Per-field confidence and human-review queue for low-confidence extractions.
* Refresh tokens / token revocation list; per-API-key scopes and rate limits.
* S3 object lifecycle (auto-expire originals), encryption-at-rest config,
  virus scanning on upload.
* Fine-grained RBAC / organizations; pagination cursors; full-text search over
  extracted data.
* Frontend: real router, optimistic updates, file drag-and-drop, result diffing.
* Load/e2e tests; contract tests for the LLM JSON schema; CI pipeline running
  `pytest` + `alembic check` + `ruff`.
```
