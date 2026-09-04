"""Application configuration, loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # App
    env: str = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # Security
    jwt_secret: str = "dev-super-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_ttl_minutes: int = 1440

    # Uploads
    max_upload_size_mb: int = 15
    allowed_mime_types: str = "application/pdf,image/png,image/jpeg,image/tiff,text/plain"

    # Rate limiting
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    # Postgres
    postgres_user: str = "docintel"
    postgres_password: str = "docintel"
    postgres_db: str = "docintel"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    # Full override (used by the test-suite to point at sqlite). Empty => build from parts.
    database_url_override: str = Field(default="", alias="DATABASE_URL")

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # S3 / MinIO   (storage_backend: s3 | memory -- "memory" is for tests/demos)
    storage_backend: str = "s3"
    s3_endpoint_url: str = "http://minio:9000"
    s3_region: str = "us-east-1"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "docintel-documents"
    s3_force_path_style: bool = True

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_document_topic: str = "document.processing"
    kafka_consumer_group: str = "docintel-workers"
    # fake | kafka  -- the test-suite / unit runs use the in-memory bus
    event_bus: str = "kafka"

    # OCR
    ocr_provider: str = "tesseract"
    ocr_timeout_seconds: int = 60
    ocr_languages: str = "eng"

    # LLM
    llm_provider: str = "fake"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = "sk-not-needed-for-fake"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: int = 45
    llm_max_retries: int = 2

    # Processing / retries
    max_processing_attempts: int = 3
    retry_backoff_base_seconds: int = 2

    # Webhooks
    webhook_max_attempts: int = 5
    webhook_backoff_base_seconds: int = 2
    webhook_timeout_seconds: int = 10

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Alembic uses a synchronous driver."""
        url = self.database_url
        return url.replace("+asyncpg", "+psycopg2").replace("+aiosqlite", "")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_mime_type_set(self) -> set[str]:
        return {m.strip() for m in self.allowed_mime_types.split(",") if m.strip()}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
