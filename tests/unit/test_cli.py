"""CLI entry point behavior."""

import json

from typer.testing import CliRunner

from linkdogger import __version__
from linkdogger.ai.generator import EmailDraft
from linkdogger.cli import app
from linkdogger.errors import AIError

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


def test_send_test_email_dry_run_requires_no_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(
        app,
        [
            "send",
            "--test",
            "me@example.com",
            "My title",
            "My body",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "test email to me@example.com" in result.output
    assert "My title" in result.output


def test_send_test_email_rejects_invalid_address(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(
        app,
        ["send", "--test", "not-an-email", "T", "B", "--dry-run"],
    )
    assert result.exit_code != 0
    assert "not a valid email address" in result.output


def test_send_test_email_without_smtp_configuration_errors(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(
        app,
        ["send", "--test", "me@example.com", "T", "B"],
    )
    assert result.exit_code != 0
    assert "SMTP is not configured" in result.output


def test_send_without_file_and_without_test_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(app, ["send"])
    assert result.exit_code != 0
    assert "--test" in result.output


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


def test_send_generate_dry_run_previews_drafts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_AI_API_KEY", "nvapi-test")
    _write_contacts_file(tmp_path / "emails.json")

    class FakeGen:
        def generate_template(self):
            return EmailDraft("Hi {name}", "Generated body.")

    monkeypatch.setattr("linkdogger.cli.DraftGenerator", lambda settings: FakeGen())
    result = runner.invoke(
        app, ["send", "emails.json", "--generate", "--dry-run", "--delay", "0"]
    )
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "Generating email template" in result.output
    assert "Hi Alice" in result.output
    assert "Generated body." in result.output
    assert "placeholder" in result.output.lower()


def test_send_generate_without_api_key_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    _write_contacts_file(tmp_path / "emails.json")
    result = runner.invoke(app, ["send", "emails.json", "--generate", "--dry-run"])
    assert result.exit_code != 0
    assert "LINKDOGGER_AI_API_KEY" in result.output


def test_send_generate_sends_via_smtp(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_AI_API_KEY", "nvapi-test")
    monkeypatch.setenv("LINKDOGGER_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LINKDOGGER_SMTP_FROM", "outbox@example.com")
    _write_contacts_file(tmp_path / "emails.json")

    class FakeGen:
        def generate_template(self):
            return EmailDraft("Hi {name}", "Generated body.")

    monkeypatch.setattr("linkdogger.cli.DraftGenerator", lambda settings: FakeGen())

    class FakeSMTP:
        messages: list = []

        def __init__(self, host, port=587, timeout=15) -> None:
            pass

        def ehlo(self) -> None:
            pass

        def starttls(self) -> None:
            pass

        def login(self, user, password) -> None:
            pass

        def send_message(self, message) -> None:
            FakeSMTP.messages.append(message)

        def quit(self) -> None:
            pass

    monkeypatch.setattr("linkdogger.mail.sender.smtplib.SMTP", FakeSMTP)
    result = runner.invoke(app, ["send", "emails.json", "--generate", "--delay", "0"])
    assert result.exit_code == 0
    assert "sent 2 of 2 emails" in result.output
    assert [m["Subject"] for m in FakeSMTP.messages] == ["Hi Alice", "Hi Bob"]


def test_doctor_checks_ai_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_AI_API_KEY", "nvapi-test")

    class FakeGen:
        def check(self) -> str:
            return "ok (123 models)"

    monkeypatch.setattr("linkdogger.cli.DraftGenerator", lambda settings: FakeGen())
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "endpoint ok: ok (123 models)" in result.output


def test_doctor_reports_ai_endpoint_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_AI_API_KEY", "nvapi-test")

    class FakeGen:
        def check(self) -> str:
            raise AIError("endpoint returned HTTP 401")

    monkeypatch.setattr("linkdogger.cli.DraftGenerator", lambda settings: FakeGen())
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "endpoint check failed: endpoint returned HTTP 401" in result.output


def test_send_generate_view_aborts_without_sending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_AI_API_KEY", "nvapi-test")
    _write_contacts_file(tmp_path / "emails.json")

    class FakeGen:
        def generate_template(self):
            return EmailDraft("Hi {name}", "Generated body.")

    monkeypatch.setattr("linkdogger.cli.DraftGenerator", lambda settings: FakeGen())
    result = runner.invoke(
        app,
        ["send", "emails.json", "--generate", "--view", "--delay", "0"],
        input="n\n",
    )
    assert result.exit_code == 0
    assert "nothing has been sent yet" in result.output
    assert "Hi Alice" in result.output
    assert "alice@example.com" in result.output
    assert "Aborted" in result.output


def test_send_generate_view_confirms_and_sends(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_AI_API_KEY", "nvapi-test")
    monkeypatch.setenv("LINKDOGGER_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LINKDOGGER_SMTP_FROM", "outbox@example.com")
    _write_contacts_file(tmp_path / "emails.json")

    class FakeGen:
        def generate_template(self):
            return EmailDraft("Hi {name}", "Generated body.")

    monkeypatch.setattr("linkdogger.cli.DraftGenerator", lambda settings: FakeGen())

    class FakeSMTP:
        messages: list = []

        def __init__(self, host, port=587, timeout=15) -> None:
            pass

        def ehlo(self) -> None:
            pass

        def starttls(self) -> None:
            pass

        def login(self, user, password) -> None:
            pass

        def send_message(self, message) -> None:
            FakeSMTP.messages.append(message)

        def quit(self) -> None:
            pass

    monkeypatch.setattr("linkdogger.mail.sender.smtplib.SMTP", FakeSMTP)
    result = runner.invoke(
        app,
        ["send", "emails.json", "--generate", "--view", "--delay", "0"],
        input="y\n",
    )
    assert result.exit_code == 0
    assert "sent 2 of 2 emails" in result.output
    assert [m["Subject"] for m in FakeSMTP.messages] == ["Hi Alice", "Hi Bob"]


def test_send_view_template_aborts_without_sending(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    _write_contacts_file(tmp_path / "emails.json")
    result = runner.invoke(
        app, ["send", "emails.json", "--view", "--delay", "0"], input="n\n"
    )
    assert result.exit_code == 0
    assert "nothing has been sent yet" in result.output
    assert "Will send to:" in result.output
    assert "alice@example.com, bob@example.com" in result.output
    assert "Aborted" in result.output


def test_send_single_email_dry_run_previews(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(
        app, ["send", "rubync2020@gmail.com", "--dry-run", "--delay", "0"]
    )
    assert result.exit_code == 0
    assert "previewed 1 of 1 emails" in result.output


def test_send_single_email_without_smtp_errors(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(app, ["send", "rubync2020@gmail.com"])
    assert result.exit_code != 0
    assert "SMTP is not configured" in result.output


def test_send_single_email_delivers(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LINKDOGGER_SMTP_FROM", "outbox@example.com")
    monkeypatch.setenv("LINKDOGGER_SMTP_FROM_NAME", "Sweet Butter")

    class FakeSMTP:
        messages: list = []

        def __init__(self, host, port=587, timeout=15) -> None:
            pass

        def ehlo(self) -> None:
            pass

        def starttls(self) -> None:
            pass

        def login(self, user, password) -> None:
            pass

        def send_message(self, message) -> None:
            FakeSMTP.messages.append(message)

        def quit(self) -> None:
            pass

    monkeypatch.setattr("linkdogger.mail.sender.smtplib.SMTP", FakeSMTP)
    result = runner.invoke(app, ["send", "rubync2020@gmail.com", "--delay", "0"])
    assert result.exit_code == 0
    assert "sent 1 of 1 emails" in result.output
    message = FakeSMTP.messages[0]
    assert message["To"] == "rubync2020@gmail.com"
    assert "rubync2020@gmail.com" in message["Subject"]


def test_send_single_email_generate_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    monkeypatch.setenv("LINKDOGGER_AI_API_KEY", "nvapi-test")

    class FakeGen:
        def generate_template(self):
            return EmailDraft("Hi {name}", "Single body.")

    monkeypatch.setattr("linkdogger.cli.DraftGenerator", lambda settings: FakeGen())
    result = runner.invoke(
        app,
        ["send", "rubync2020@gmail.com", "--generate", "--dry-run", "--delay", "0"],
    )
    assert result.exit_code == 0
    assert "Hi rubync2020@gmail.com" in result.output
    assert "Single body." in result.output


def test_send_single_email_view_aborts(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    result = runner.invoke(
        app,
        ["send", "rubync2020@gmail.com", "--view", "--delay", "0"],
        input="n\n",
    )
    assert result.exit_code == 0
    assert "Will send to: rubync2020@gmail.com" in result.output
    assert "Aborted" in result.output


def test_send_json_suffix_always_means_contacts_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from a local .env
    _write_contacts_file(tmp_path / "alice@example.com.json")
    result = runner.invoke(
        app, ["send", "alice@example.com.json", "--dry-run", "--delay", "0"]
    )
    assert result.exit_code == 0
    assert "previewed 2 of 2 emails" in result.output
