import os
from pathlib import Path

from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalize_database_url(url: str) -> str:
    normalized = url.strip()
    if normalized.startswith("postgres://"):
        return "postgresql+psycopg://" + normalized[len("postgres://") :]
    if normalized.startswith("postgresql://"):
        return "postgresql+psycopg://" + normalized[len("postgresql://") :]
    return normalized


class Settings(BaseModel):
    app_name: str = "A.S.A.P. Backend"
    app_version: str = "0.1.0"
    database_url: str = Field(
        default_factory=lambda: _normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./asap.db"))
    )
    auto_create_tables: bool = Field(default_factory=lambda: _env_bool("AUTO_CREATE_TABLES", True))

    lead_confirm_url_base: str = Field(
        default_factory=lambda: os.getenv(
            "LEAD_CONFIRM_URL_BASE",
            "http://127.0.0.1:8000/api/leads/confirm",
        )
    )
    lead_token_ttl_hours: int = Field(default_factory=lambda: _env_int("LEAD_TOKEN_TTL_HOURS", 24))

    smtp_host: str | None = Field(default_factory=lambda: os.getenv("SMTP_HOST"))
    smtp_port: int | None = Field(default_factory=lambda: _env_optional_int("SMTP_PORT"))
    smtp_provider: str = Field(default_factory=lambda: os.getenv("SMTP_PROVIDER", "custom"))
    smtp_username: str | None = Field(default_factory=lambda: os.getenv("SMTP_USERNAME"))
    smtp_password: str | None = Field(default_factory=lambda: os.getenv("SMTP_PASSWORD"))
    smtp_from_name: str = Field(default_factory=lambda: os.getenv("SMTP_FROM_NAME", "A.S.A.P."))
    smtp_from_email: str = Field(
        default_factory=lambda: os.getenv("SMTP_FROM_EMAIL", "no-reply@asap-health.app")
    )
    smtp_reply_to: str | None = Field(default_factory=lambda: os.getenv("SMTP_REPLY_TO"))
    smtp_use_tls: bool = Field(default_factory=lambda: _env_bool("SMTP_USE_TLS", True))
    smtp_use_ssl: bool = Field(default_factory=lambda: _env_bool("SMTP_USE_SSL", False))
    smtp_timeout_seconds: int = Field(default_factory=lambda: _env_int("SMTP_TIMEOUT_SECONDS", 20))

    auth_secret_key: str = Field(
        default_factory=lambda: os.getenv(
            "AUTH_SECRET_KEY",
            "cambia-esta-clave-en-produccion-asap",
        )
    )
    auth_algorithm: str = Field(default_factory=lambda: os.getenv("AUTH_ALGORITHM", "HS256"))
    auth_access_token_expires_minutes: int = Field(
        default_factory=lambda: _env_int("AUTH_ACCESS_TOKEN_EXPIRES_MINUTES", 60 * 24 * 30)
    )
    auth_issuer: str = Field(default_factory=lambda: os.getenv("AUTH_ISSUER", "asap-backend"))

    admin_dataset_export_key: str = Field(
        default_factory=lambda: os.getenv("ADMIN_DATASET_EXPORT_KEY", "asap-admin-dev-key")
    )

    ml_sleep_model_path: str = Field(
        default_factory=lambda: os.getenv("ML_SLEEP_MODEL_PATH", str(BASE_DIR / "artifacts" / "sleep_model.joblib"))
    )


settings = Settings()
