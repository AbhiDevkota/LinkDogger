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
        "GITHUB_EMAIL_PATCH_TIMEOUT_SECONDS",
        "MAX_RESULTS",
        "DISCOVERY_BACKEND",
        "GITHUB_TOKEN",
        "LINKEDIN_SESSION_FILE",
        "LINKEDIN_HEADLESS",
    ):  # noqa: E501
        monkeypatch.delenv(f"LINKDOGGER_{key}", raising=False)


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.web_host == "127.0.0.1"
    assert settings.web_port == 8000
    assert settings.request_timeout_seconds == 10.0
    assert settings.github_email_patch_timeout_seconds == 10.0
    assert settings.max_results == 100
    assert settings.discovery_backend == "mock"
    assert settings.github_token is None
    assert settings.linkedin_session_file is None
    assert settings.linkedin_headless is True


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINKDOGGER_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LINKDOGGER_WEB_PORT", "9000")
    monkeypatch.setenv("LINKDOGGER_MAX_RESULTS", "50")
    monkeypatch.setenv("LINKDOGGER_DISCOVERY_BACKEND", "github")
    monkeypatch.setenv("LINKDOGGER_GITHUB_TOKEN", "gh_test_token")
    monkeypatch.setenv("LINKDOGGER_LINKEDIN_SESSION_FILE", "linkedin-session.json")
    monkeypatch.setenv("LINKDOGGER_LINKEDIN_HEADLESS", "false")
    monkeypatch.setenv("LINKDOGGER_GITHUB_EMAIL_PATCH_TIMEOUT_SECONDS", "0")

    settings = Settings(_env_file=None)
    assert settings.log_level == "DEBUG"
    assert settings.web_port == 9000
    assert settings.max_results == 50
    assert settings.discovery_backend == "github"
    assert settings.github_token == "gh_test_token"
    assert settings.linkedin_session_file == "linkedin-session.json"
    assert settings.linkedin_headless is False
    assert settings.github_email_patch_timeout_seconds == 0


def test_unknown_environment_variables_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LINKDOGGER_UNRELATED", "value")
    settings = Settings(_env_file=None)
    assert settings.web_port == 8000
