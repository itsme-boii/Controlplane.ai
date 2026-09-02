"""Environment-based configuration. No secrets in code (see .env.example)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Foundation-model backend
    model_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    model_timeout_s: float = 60.0

    # Load every detector model at startup so the first checked request is not
    # charged for cold model loading. Turned off in tests (fakes need no models).
    detector_warmup: bool = True

    # Datastores
    database_url: str = "postgresql+asyncpg://controlplane:controlplane@postgres:5432/controlplane"
    redis_url: str = "redis://redis:6379/0"

    # Gateway
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    log_level: str = "INFO"

    # Directory holding the versioned YAML policy packs (Phase 2).
    policies_dir: str = Field(default="/app/policies")

    # Phase 5: Ledger and Cache
    ledger_enabled: bool = True
    ledger_ttl_seconds: int = 86400
    ledger_decay: float = 0.85
    ledger_escalation_threshold: float = 1.2
    judge_cache_ttl_s: int = 86400

    # Phase 6: Mailtrap Actions
    mailtrap_api_token: str = ""
    mailtrap_inbox_id: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
