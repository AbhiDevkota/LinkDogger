"""CLI entry point behavior."""

import json

from typer.testing import CliRunner

from linkdogger import __version__
from linkdogger.cli import app

runner = CliRunner()


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert f"LinkDogger {__version__}" in result.output


def test_help_shows_usage() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "search" in result.output


def test_help_lists_all_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("search", "login", "linkedin-login", "serve", "doctor", "config"):
        assert command in result.output


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "--version" in result.output


def test_config_shows_effective_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "LINKDOGGER_MAX_RESULTS = 100" in result.output
    assert "LINKDOGGER_GITHUB_TOKEN = (not set)" in result.output
    assert "LINKDOGGER_LINKEDIN_PASSWORD = (not set)" in result.output


def test_doctor_reports_provider_status(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "diagnostics" in result.output
    assert "mock" in result.output
    assert "github" in result.output
    assert "linkedin" in result.output
    assert "not configured" in result.output
    assert "x" in result.output


def test_search_shows_results() -> None:
    result = runner.invoke(app, ["search", "Acme", "--provider", "mock"])
    assert result.exit_code == 0
    assert "Acme Corporation" in result.output
    assert "publicly discoverable people" in result.output
    assert "Alex Sample" in result.output


def test_search_unknown_company_reports_not_found() -> None:
    result = runner.invoke(app, ["search", "Nonexistent Company", "--provider", "mock"])
    assert result.exit_code == 1
    assert "Company not found" in result.output


def test_search_with_log_shows_results() -> None:
    result = runner.invoke(app, ["search", "Acme", "--log", "--provider", "mock"])
    assert result.exit_code == 0
    assert "Acme Corporation" in result.output
    assert "Alex Sample" in result.output


def test_search_reports_profiles_excluded_by_filters() -> None:
    result = runner.invoke(
        app, ["search", "Acme", "--provider", "mock", "--location", "nowhere"]
    )
    assert result.exit_code == 0
    assert "excluded by your filters" in result.output
    assert "3" in result.output.split("excluded")[0]


def test_search_json_output() -> None:
    result = runner.invoke(app, ["search", "Acme", "--json", "--provider", "mock"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1.0"
    assert payload["query"] == "Acme"
    assert payload["company"]["name"] == "Acme Corporation"
    assert payload["count"] == 3
    assert payload["results"][0]["name"] == "Alex Sample"


def test_search_json_unknown_company() -> None:
    result = runner.invoke(
        app, ["search", "Nonexistent Company", "--json", "--provider", "mock"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["company"] is None
    assert payload["count"] == 0


def test_search_missing_company_errors() -> None:
    result = runner.invoke(app, ["search"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_search_invalid_provider_errors() -> None:
    result = runner.invoke(app, ["search", "Acme", "--provider", "bogus"])
    assert result.exit_code != 0
    assert "invalid provider" in result.output


def test_hybrid_flag_is_shorthand_for_hybrid_provider() -> None:
    result = runner.invoke(app, ["search", "Acme", "--hybrid", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "warnings" in payload


def test_linkedin_provider_reports_discovery_gap(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(app, ["search", "Microsoft", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["count"] == 0
    assert any("LinkedIn" in w for w in payload["warnings"])


def test_linkedin_login_without_cookie_file_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(app, ["linkedin-login"])
    assert result.exit_code != 0
    assert "LINKDOGGER_LINKEDIN_COOKIE_FILE" in result.output


def test_linkedin_login_saves_cookie_file(tmp_path, monkeypatch) -> None:
    cookie_file = tmp_path / "linkedin-cookies.json"
    monkeypatch.setenv("LINKDOGGER_LINKEDIN_COOKIE_FILE", str(cookie_file))
    result = runner.invoke(
        app,
        ["linkedin-login"],
        input="li-at-value\najax:1234567890\n",
    )
    assert result.exit_code == 0
    payload = json.loads(cookie_file.read_text(encoding="utf-8"))
    assert payload == {"li_at": "li-at-value", "JSESSIONID": "ajax:1234567890"}


def test_login_command_saves_cookie_file(tmp_path, monkeypatch) -> None:
    cookie_file = tmp_path / "linkedin-cookies.json"
    monkeypatch.setenv("LINKDOGGER_LINKEDIN_COOKIE_FILE", str(cookie_file))
    result = runner.invoke(
        app,
        ["login"],
        input="li-at-value\najax:1234567890\n",
    )
    assert result.exit_code == 0
    payload = json.loads(cookie_file.read_text(encoding="utf-8"))
    assert payload == {"li_at": "li-at-value", "JSESSIONID": "ajax:1234567890"}


def test_linkedin_login_rejects_empty_cookies(tmp_path, monkeypatch) -> None:
    cookie_file = tmp_path / "linkedin-cookies.json"
    monkeypatch.setenv("LINKDOGGER_LINKEDIN_COOKIE_FILE", str(cookie_file))
    result = runner.invoke(app, ["linkedin-login"], input="\n")
    assert result.exit_code != 0
    assert not cookie_file.exists()
