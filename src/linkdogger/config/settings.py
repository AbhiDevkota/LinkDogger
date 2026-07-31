"""Application configuration.

Values are read from environment variables prefixed with ``LINKDOGGER_``
(e.g. ``LINKDOGGER_LOG_LEVEL``) and from a local ``.env`` file when present.
Secrets and API keys must never be committed; provide them only through the
environment or a local ``.env`` file (see ``.env.example``).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for LinkDogger."""

    model_config = SettingsConfigDict(
        env_prefix="LINKDOGGER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    request_timeout_seconds: float = 10.0
    max_results: int = 100


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance shared across the application."""
    return Settings()
