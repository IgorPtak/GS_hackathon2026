"""Process settings read from environment variables (see .env.example)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every service reads the same settings; each uses only what it needs.

    Defaults point at localhost so tests and scripts run on the host against the compose stack;
    inside compose, `.env.example` / `.env` override them with service host names.
    """

    model_config = SettingsConfigDict(env_file=None, extra="ignore", frozen=True)

    service_name: str = Field(default="alerting", description="Set per compose service.")
    log_level: str = "INFO"

    database_url: str = "postgresql://alerting:change-me-local-only@localhost:5432/alerting"
    database_pool_min_size: int = 1
    database_pool_max_size: int = 10
    redis_url: str = "redis://localhost:6379/0"

    config_dir: str = "config"
    public_base_url: str = "http://localhost:5173"

    channel_allowed_hosts: list[str] = Field(
        default=["mock-gateway", "mailpit", "localhost", "127.0.0.1"],
        description="Hosts channel plugins may contact (env CHANNEL_ALLOWED_HOSTS, JSON list).",
    )

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mock_gateway_url: str = "http://localhost:8090"

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    llm_allowed_hosts: str = "ollama,localhost,127.0.0.1"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_timeout_seconds: float = 30.0

    prometheus_url: str = "http://localhost:9090"
    metrics_port: int = Field(default=9100, description="Workers serve /metrics and /healthz here.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are read once per process; tests construct `Settings(...)` directly instead."""
    return Settings()
