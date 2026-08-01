"""Application configuration.

Values are read from environment variables prefixed with ``LINKDOGGER_``
(e.g. ``LINKDOGGER_LOG_LEVEL``) and from a local ``.env`` file when present.
Secrets and API keys must never be committed; provide them only through the
environment or a local ``.env`` file (see ``.env.example``).
"""

from functools import lru_cache
from typing import Literal

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
    github_email_patch_timeout_seconds: float | None = 10.0
    max_results: int = 100
    discovery_backend: Literal["mock", "github"] = "mock"
    github_token: str | None = None
    linkedin_email: str | None = None
    linkedin_password: str | None = None
    linkedin_cookies_dir: str | None = None
    linkedin_cookie_file: str | None = None

    # Local IPC server (other processes on this machine).
    ipc_host: str = "127.0.0.1"
    ipc_port: int = 8123
    ipc_token: str | None = None

    # SMTP outbox (send command).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_from_name: str | None = None
    smtp_starttls: bool = True

    # IMAP inbox (watch command).
    imap_host: str | None = None
    imap_port: int = 993
    imap_username: str | None = None
    imap_password: str | None = None
    imap_folder: str = "INBOX"
    imap_starttls: bool = False

    # AI generation (send --generate), via an OpenAI-compatible endpoint
    # such as NVIDIA NIM (build.nvidia.com).
    ai_api_key: str | None = None
    ai_model: str = "deepseek-ai/deepseek-v4-flash"
    ai_base_url: str = "https://integrate.api.nvidia.com/v1"
    ai_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance shared across the application."""
    return Settings()
