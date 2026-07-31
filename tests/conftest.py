"""Shared test configuration."""

import pytest

from linkdogger.config.settings import get_settings


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the mock backend so tests never hit real APIs or the local .env.

    Environment variables take precedence over the ``.env`` file in
    pydantic-settings, and the cached settings are cleared so every test
    re-reads the isolated configuration.
    """
    monkeypatch.setenv("LINKDOGGER_DISCOVERY_BACKEND", "mock")
    monkeypatch.delenv("LINKDOGGER_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("LINKDOGGER_LINKEDIN_SESSION_FILE", raising=False)
    get_settings.cache_clear()
