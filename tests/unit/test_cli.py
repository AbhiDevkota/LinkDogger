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


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "--version" in result.output


def test_search_shows_results() -> None:
    result = runner.invoke(app, ["search", "Acme"])
    assert result.exit_code == 0
    assert "Acme Corporation" in result.output
    assert "publicly discoverable people" in result.output
    assert "Alex Sample" in result.output


def test_search_unknown_company_reports_not_found() -> None:
    result = runner.invoke(app, ["search", "Nonexistent Company"])
    assert result.exit_code == 1
    assert "Company not found" in result.output


def test_search_with_log_shows_results() -> None:
    result = runner.invoke(app, ["search", "Acme", "--log"])
    assert result.exit_code == 0
    assert "Acme Corporation" in result.output
    assert "Alex Sample" in result.output


def test_search_json_output() -> None:
    result = runner.invoke(app, ["search", "Acme", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["schema_version"] == "1.0"
    assert payload["query"] == "Acme"
    assert payload["company"]["name"] == "Acme Corporation"
    assert payload["count"] == 3
    assert payload["results"][0]["name"] == "Alex Sample"


def test_search_json_unknown_company() -> None:
    result = runner.invoke(app, ["search", "Nonexistent Company", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["company"] is None
    assert payload["count"] == 0


def test_search_missing_company_errors() -> None:
    result = runner.invoke(app, ["search"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output
