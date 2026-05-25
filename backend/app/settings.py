"""Application settings using Pydantic BaseSettings.

Configuration is loaded from environment variables and .env files.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator
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
    db_pool_size: int = Field(default=5, description="Connection pool size")
    db_max_overflow: int = Field(default=10, description="Max overflow connections")
    db_conn_prewarm: bool = Field(
        default=False, description="Pre-warm database connection pool at startup"
    )
    db_sqlite_dir: str = Field(default="./data", description="SQLite database directory")

    # ==================== Redis ====================
    # NOTE: Uncomment and configure if enable_redis is true
    # redis_host: str = "localhost"
    # redis_port: int = 6379
    # redis_user: str | None = None
    # redis_pass: str | None = None
    # redis_base: int | None = None
    # redis_db: int = 0
    # redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # ==================== Kafka / MSK ====================
    # NOTE: Uncomment and configure if enable_kafka is true
    # kafka_bootstrap_servers: str = Field(
    #     default="localhost:9092",
    #     description="Kafka bootstrap servers (comma-separated for MSK)"
    # )
    # kafka_client_id: str = "backend"
    # kafka_group_id: str = "backend-consumer-group"
    # kafka_auto_offset_reset: str = "earliest"
    # kafka_enable_auto_commit: bool = True
    # kafka_security_protocol: str = "PLAINTEXT"  # or "SASL_SSL" for MSK
    # kafka_sasl_mechanism: str = "OAUTHBEARER"  # or "PLAIN"
    # kafka_sasl_username: str | None = None
    # kafka_sasl_password: str | None = None
    # kafka_ssl_cafile: str | None = None
    # kafka_ssl_certfile: str | None = None
    # kafka_ssl_keyfile: str | None = None

    # ==================== Temporal ====================
    # NOTE: Uncomment and configure if enable_temporal is true
    # temporal_host: str = "localhost"
    # temporal_port: int = 7233
    # temporal_namespace: str = "default"
    # temporal_task_queue: str = "backend-tasks"
    # temporal_tls_cert_path: str | None = None
    # temporal_tls_key_path: str | None = None
    # temporal_tls_ca_path: str | None = None

    # ==================== AWS S3 ====================
    # NOTE: Uncomment and configure for S3 integration
    # aws_access_key_id: str | None = None
    # aws_secret_access_key: str | None = None
    # aws_region: str = "us-east-1"
    # aws_s3_bucket: str = "backend-data"
    # aws_s3_endpoint_url: str | None = None  # For LocalStack or custom S3-compatible storage
    # aws_s3_presigned_expiry: int = 3600  # seconds

    # ==================== OAuth / Auth ====================
    # NOTE: Uncomment and configure if enable_oauth is true
    # oauth_google_client_id: str | None = None
    # oauth_google_client_secret: str | None = None
    # oauth_google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    # oauth_github_client_id: str | None = None
    # oauth_github_client_secret: str | None = None
    # oauth_github_redirect_uri: str = "http://localhost:8000/auth/github/callback"
    # oauth_auth0_domain: str | None = None
    # oauth_auth0_client_id: str | None = None
    # oauth_auth0_client_secret: str | None = None
    # oauth_auth0_audience: str | None = None

    # ==================== JWT / Auth ====================
    jwt_secret_key: str = "changeme-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 1 week
    jwt_issuer: str = "http://localhost"
    jwt_audience: str = "http://localhost"

    @model_validator(mode="after")
    def validate_settings(self) -> Settings:
        if self.environment == "production":
            if self.jwt_secret_key == "changeme-in-production":
                raise ValueError(
                    "JWT_SECRET_KEY must be set in production. "
                    "Set the JWT_SECRET_KEY environment variable with a secure random value."
                )
            if self.session_secret_key == "changeme-in-production":
                raise ValueError(
                    "SESSION_SECRET_KEY must be set in production. "
                    "Set the SESSION_SECRET_KEY environment variable with a secure random value."
                )
        elif self.jwt_secret_key == "changeme-in-production":
            import warnings

            warnings.warn(
                "JWT secret key is set to the insecure default 'changeme-in-production'. "
                "Change it via the JWT_SECRET_KEY env var for security.",
                stacklevel=2,
            )
        return self

    # ==================== Session ====================
    session_secret_key: str = Field(
        default="changeme-in-production",
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

    # ==================== OpenTelemetry (optional) ====================
    opentelemetry_endpoint: str | None = None
    opentelemetry_service_name: str = "backend"

    # ==================== Sentry (optional) ====================
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1
    sentry_profiles_sample_rate: float = 0.1

    # ==================== Datadog (optional) ====================
    datadog_on: bool = False
    datadog_agent_host: str = "localhost"
    datadog_agent_port: int = 8125

    # ==================== Task Queue (Celery-like) ====================
    # NOTE: Uncomment and configure for task queue support
    # task_queue_broker_url: str = "redis://localhost:6379/0"
    # task_queue_result_backend: str = "redis://localhost:6379/1"
    # task_queue_default_queue: str = "default"
    # task_queue_task_serializer: str = "json"
    # task_queue_result_serializer: str = "json"
    # task_queue_accept_content: list[str] = ["json"]
    # task_queue_timezone: str = "UTC"
    # task_queue_enable_utc: bool = True

    # ==================== Thread Pools ====================
    default_main_thread_pool_size: int = 40


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create global settings instance.

    Returns:
        Settings singleton.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing).

    Returns:
        New Settings instance.
    """
    global _settings
    _settings = Settings()
    return _settings


# Convenience accessor
settings = get_settings()
