"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("file_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("document_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("status", sa.String(16), nullable=False, server_default="UPLOADED"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_user_status", "documents", ["user_id", "status"])
    op.create_index("ix_documents_user_created", "documents", ["user_id", "created_at"])
    op.create_index("ix_documents_idempotency_key", "documents", ["idempotency_key"])
    op.create_index("ix_documents_checksum_sha256", "documents", ["checksum_sha256"])

    op.create_table(
        "document_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("extracted_data", sa.JSON(), nullable=False),
        sa.Column("masked_data", sa.JSON(), nullable=False),
        sa.Column("ocr_provider", sa.String(32), nullable=True),
        sa.Column("llm_provider", sa.String(32), nullable=True),
        sa.Column("llm_model", sa.String(64), nullable=True),
        sa.Column("ocr_char_count", sa.Integer(), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_document_results_document_id", "document_results",
                    ["document_id"], unique=True)

    op.create_table(
        "processing_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="started"),
        sa.Column("stage", sa.String(32), nullable=True),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_processing_attempts_document_id", "processing_attempts", ["document_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    op.create_table(
        "webhooks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_webhooks_user_id", "webhooks", ["user_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("webhook_id", sa.Uuid(),
                  sa.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", sa.Uuid(),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_webhook_deliveries_webhook_id", "webhook_deliveries", ["webhook_id"])
    op.create_index("ix_webhook_deliveries_document_id", "webhook_deliveries", ["document_id"])
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("document_id", sa.Uuid(),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_id_key"),
    )


def downgrade() -> None:
    for table in (
        "idempotency_keys",
        "webhook_deliveries",
        "webhooks",
        "api_keys",
        "audit_logs",
        "processing_attempts",
        "document_results",
        "documents",
        "users",
    ):
        op.drop_table(table)
