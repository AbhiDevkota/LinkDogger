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


def test_search_export_email_writes_emails_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env, control file location
    result = runner.invoke(
        app, ["search", "Acme", "--provider", "mock", "--export", "email"]
    )
    assert result.exit_code == 0
    assert "2 email(s) to acme-corporation.emails.json" in result.output
    payload = json.loads(
        (tmp_path / "acme-corporation.emails.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == "1.0"
    assert payload["query"] == "Acme"
    assert payload["company"] == "Acme Corporation"
    assert payload["count"] == 2
    assert "alex.sample@example.com" in payload["emails"]
    assert "taylor.sample@example.com" in payload["emails"]


def test_search_export_email_unknown_company_still_writes_file(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env, control file location
    result = runner.invoke(
        app,
        ["search", "Nonexistent Company", "--provider", "mock", "--export", "email"],
    )
    assert result.exit_code == 1
    payload = json.loads(
        (tmp_path / "nonexistent-company.emails.json").read_text(encoding="utf-8")
    )
    assert payload["count"] == 0
    assert payload["emails"] == []


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


def _write_contacts_file(path) -> None:
    path.write_text(
        json.dumps(
            {
                "emails": ["alice@example.com", "bob@example.com"],
                "people": [
                    {"name": "Alice", "email": "alice@example.com"},
                    {"name": "Bob", "email": "bob@example.com"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_send_dry_run_previews_without_smtp(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    _write_contacts_file(tmp_path / "emails.json")
    result = runner.invoke(app, ["send", "emails.json", "--dry-run", "--delay", "0"])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "previewed 2 of 2 emails" in result.output


def test_send_without_smtp_configuration_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    _write_contacts_file(tmp_path / "emails.json")
    result = runner.invoke(app, ["send", "emails.json"])
    assert result.exit_code != 0
    assert "SMTP is not configured" in result.output


def test_watch_once_reports_replies(tmp_path, monkeypatch) -> None:
    import email as email_module

    monkeypatch.chdir(tmp_path)  # isolate from a local .env

    class FakeIMAP:
        def __init__(self, host, port=993, timeout=15) -> None:
            pass

        def login(self, user, password) -> str:
            return "OK"

        def select(self, folder="INBOX") -> tuple:
            return ("OK", [b"1"])

        def uid(self, command, *args) -> tuple:
            if command == "SEARCH":
                return ("OK", [b"1"])
            message = email_module.message.EmailMessage()
            message["From"] = "Alice Example <alice@example.com>"
            message["Subject"] = "Re: hello"
            message.set_content("Happy to chat!")
            raw = message.as_bytes()
            return ("OK", [(f"1 (UID 1 RFC822 {{{len(raw)}}}".encode(), raw), b")"])

        def logout(self) -> str:
            return "BYE"

    monkeypatch.setattr(
        "linkdogger.mail.observer.imaplib.IMAP4_SSL",
        lambda *a, **k: FakeIMAP(*a, **k),
    )
    monkeypatch.setenv("LINKDOGGER_IMAP_HOST", "imap.example.com")
    _write_contacts_file(tmp_path / "emails.json")
    result = runner.invoke(app, ["watch", "emails.json", "--once", "--interval", "0"])
    assert result.exit_code == 0
    assert "Reply from alice@example.com" in result.output
    assert "Re: hello" in result.output
