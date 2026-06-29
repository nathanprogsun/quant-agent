"""Application settings using Pydantic BaseSettings.

Configuration is loaded from environment variables and .env files.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    All settings can be overridden via environment variables.
    For example, `database_url` can be set via `DATABASE_URL` env var.

    model_config: Use env file, case-sensitive, extra fields ignored.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==================== Application ====================
    app_name: str = "backend"
    environment: Literal["local", "development", "staging", "production"] = "local"
    debug: bool = False

    # ==================== Database ====================
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data.db",
        description="SQLAlchemy async database URL (sqlite, postgres, etc.)",
    )
    db_backend: Literal["memory", "sqlite", "postgres"] = "sqlite"
    db_echo: bool = Field(default=False, description="Echo SQL to logs")
    db_sqlite_dir: str = Field(default="./data", description="SQLite database directory")

    # ==================== JWT / Auth ====================
    jwt_secret_key: SecretStr = SecretStr("changeme-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 1 week
    jwt_issuer: str = "http://localhost"
    jwt_audience: str = "http://localhost"

    # ==================== Session ====================
    session_secret_key: SecretStr = Field(
        default=SecretStr("changeme-in-production"),
        description="Secret key for session encryption",
    )

    # ==================== Logging ====================
    log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ==================== CORS ====================
    cors_allow_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]  # Restrict in production
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    # ==================== LLM ====================
    openai_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", validation_alias="OPENAI_BASE_URL"
    )
    model: str = Field(default="gpt-4o-mini", validation_alias="MODEL")

    # ==================== jq_kb embedding (HTTP provider) ====================
    # Preferred: JQKB_* (provider-agnostic). Legacy aliases: OPENAI_*.
    jq_kb_embedding_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("JQKB_EMBEDDING_API_KEY", "OPENAI_EMBEDDING_API_KEY"),
    )
    jq_kb_embedding_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("JQKB_EMBEDDING_BASE_URL", "OPENAI_EMBEDDING_BASE_URL"),
    )
    jq_kb_embedding_model: str = Field(
        default="",
        validation_alias=AliasChoices("JQKB_EMBEDDING_MODEL", "OPENAI_EMBEDDING_MODEL"),
    )
    jq_kb_embedding_max_chars: int = Field(
        default=6000,
        validation_alias=AliasChoices("JQKB_EMBEDDING_MAX_CHARS", "OPENAI_EMBEDDING_MAX_CHARS"),
    )
    jq_kb_code_chunk_max_chars: int = Field(
        default=3000,
        validation_alias=AliasChoices("JQKB_CODE_CHUNK_MAX_CHARS", "OPENAI_CODE_CHUNK_MAX_CHARS"),
    )

    # ==================== jq_kb rerank (cross-encoder) ====================
    jq_kb_rerank_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("JQKB_RERANK_API_KEY", "OPENAI_RERANK_API_KEY"),
    )
    jq_kb_rerank_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("JQKB_RERANK_BASE_URL", "OPENAI_RERANK_BASE_URL"),
    )
    jq_kb_rerank_model: str = Field(
        default="",
        validation_alias=AliasChoices("JQKB_RERANK_MODEL", "OPENAI_RERANK_MODEL"),
    )

    # ==================== Checkpointer ====================
    checkpointer_backend: Literal["memory", "sqlite", "postgres"] = "sqlite"
    checkpointer_connection_string: str = "checkpoints.db"

    # ==================== StreamBridge ====================
    stream_bridge_queue_maxsize: int = 256

    # ==================== RunManager ====================
    run_manager_max_runs: int = 1000
    run_manager_ttl_seconds: int = 3600

    # ==================== JoinQuant / jqcli ====================
    jqcli_token: SecretStr | None = Field(
        default=None,
        validation_alias="JQCLI_TOKEN",
        description="JoinQuant API token (server env only)",
    )
    jqcli_cookie: SecretStr | None = Field(
        default=None,
        validation_alias="JQCLI_COOKIE",
        description="JoinQuant session cookie (server env only)",
    )
    jqcli_api_base: str = Field(
        default="https://www.joinquant.com",
        validation_alias="JQCLI_API_BASE",
        description="JoinQuant API base URL",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> None:
    """Clear the lru_cache so the next get_settings() call rebuilds it.

    Primarily used by tests to pick up env-var changes between cases.
    """
    get_settings.cache_clear()


settings = get_settings()
