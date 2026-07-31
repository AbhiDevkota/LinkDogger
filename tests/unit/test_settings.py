"""Configuration defaults and environment overrides."""

import pytest

from linkdogger.config.settings import Settings


@pytest.fixture(autouse=True)
def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "LOG_LEVEL",
        "WEB_HOST",
        "WEB_PORT",
        "REQUEST_TIMEOUT_SECONDS",
        "MAX_RESULTS",
    ):  # noqa: E501
        monkeypatch.delenv(f"LINKDOGGER_{key}", raising=False)


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.web_host == "127.0.0.1"
    assert settings.web_port == 8000
    assert settings.request_timeout_seconds == 10.0
    assert settings.max_results == 100


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKDOGGER_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LINKDOGGER_WEB_PORT", "9000")
    monkeypatch.setenv("LINKDOGGER_MAX_RESULTS", "50")

    settings = Settings(_env_file=None)
    assert settings.log_level == "DEBUG"
    assert settings.web_port == 9000
    assert settings.max_results == 50


def test_unknown_environment_variables_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKDOGGER_UNRELATED", "value")
    settings = Settings(_env_file=None)
    assert settings.web_port == 8000
