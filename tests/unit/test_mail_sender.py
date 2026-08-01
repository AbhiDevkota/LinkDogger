"""SMTP sender and contacts loader."""

import json
from pathlib import Path

import pytest

from linkdogger.config.settings import Settings
from linkdogger.errors import MailError
from linkdogger.mail.contacts import Contact, load_contacts, validate_email
from linkdogger.mail.sender import (
    DEFAULT_BODY,
    DEFAULT_SUBJECT,
    build_message,
    send_emails,
    send_generated,
    send_test_email,
)


class FakeSMTP:
    """Records sent messages instead of delivering them."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int = 0, timeout: float = 0) -> None:
        self.host = host
        self.port = port
        self.messages: list[object] = []
        self.starttls_called = False
        self.login_credentials: tuple[str, str] | None = None
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def ehlo(self) -> None:
        pass

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, user: str, password: str) -> None:
        self.login_credentials = (user, password)

    def send_message(self, message: object) -> None:
        self.messages.append(message)

    def quit(self) -> None:
        self.quit_called = True


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr("linkdogger.mail.sender.smtplib.SMTP", FakeSMTP)


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        smtp_host="smtp.example.com",
        smtp_username="outbox@example.com",
        smtp_password="hunter2",
        smtp_from="outbox@example.com",
        smtp_from_name="Ada Example",
        **overrides,
    )


def _contacts() -> list[Contact]:
    return [
        Contact(email="alice@example.com", name="Alice", company="Acme"),
        Contact(email="bob@example.com", name="Bob", company="Acme"),
    ]


def test_load_contacts_from_exported_payload(tmp_path: Path) -> None:
    path = tmp_path / "emails.json"
    path.write_text(
        json.dumps(
            {
                "emails": [
                    "alice@example.com",
                    "bob@example.com",
                    "alice@example.com",
                ],
                "people": [
                    {
                        "name": "Alice",
                        "company": "Acme",
                        "position": "Engineer",
                        "email": "alice@example.com",
                    },
                    {
                        "name": "Bob",
                        "company": "Acme",
                        "position": "Designer",
                        "email": "bob@example.com",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    contacts = load_contacts(path)
    assert [c.email for c in contacts] == ["alice@example.com", "bob@example.com"]
    assert contacts[0].position == "Engineer"


def test_load_contacts_from_bare_list_and_objects(tmp_path: Path) -> None:
    path = tmp_path / "emails.json"
    path.write_text(
        json.dumps(["A@Example.com ", {"email": "bob@example.com", "name": "Bob"}]),
        encoding="utf-8",
    )
    contacts = load_contacts(path)
    assert [c.email for c in contacts] == ["a@example.com", "bob@example.com"]
    assert contacts[0].name is None
    assert contacts[1].name == "Bob"


def test_load_contacts_from_full_search_export(tmp_path: Path) -> None:
    path = tmp_path / "search.json"
    path.write_text(
        json.dumps(
            {
                "results": [
                    {"name": "Alice", "email": "alice@example.com"},
                    {"name": "No Email"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert [c.email for c in load_contacts(path)] == ["alice@example.com"]


def test_load_contacts_rejects_bad_emails_and_injection(tmp_path: Path) -> None:
    path = tmp_path / "emails.json"
    path.write_text(
        json.dumps(
            [
                "not-an-email",
                "evil@example.com\r\nBcc: victim@example.com",
                "ok@example.com",
            ]
        ),
        encoding="utf-8",
    )
    assert [c.email for c in load_contacts(path)] == ["ok@example.com"]


def test_load_contacts_rejects_unreadable_or_empty(tmp_path: Path) -> None:
    with pytest.raises(MailError, match="could not read"):
        load_contacts(tmp_path / "missing.json")
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps(["nope@"]), encoding="utf-8")
    with pytest.raises(MailError, match="no valid email"):
        load_contacts(empty)


def test_build_message_personalizes_and_headers() -> None:
    message = build_message(
        Contact(email="alice@example.com", name="Alice", company="Acme"),
        "Hi {name} at {company}",
        "Hello {name},\n\nYour position: {position}\n\n{from_name}",
        _settings(),
    )
    assert message["To"] == "alice@example.com"
    assert message["From"] == "Ada Example <outbox@example.com>"
    assert message["Subject"] == "Hi Alice at Acme"
    assert "Hello Alice," in message.get_content()
    assert "Your position:" in message.get_content()
    assert "Ada Example" in message.get_content()
    assert message["Message-ID"]
    assert message["X-LinkDogger"] == "1"


def test_send_emails_delivers_personalized_messages() -> None:
    report = send_emails(_contacts(), settings=_settings())
    assert report.total == 2
    assert report.sent == ["alice@example.com", "bob@example.com"]
    assert not report.failed
    smtp = FakeSMTP.instances[0]
    assert smtp.starttls_called
    assert smtp.login_credentials == ("outbox@example.com", "hunter2")
    assert len(smtp.messages) == 2
    assert smtp.quit_called


def test_send_emails_isolates_per_recipient_failures(monkeypatch) -> None:
    class FlakySMTP(FakeSMTP):
        def send_message(self, message: object) -> None:
            if "bob" in str(message):
                raise OSError("connection reset")
            self.messages.append(message)

    monkeypatch.setattr("linkdogger.mail.sender.smtplib.SMTP", FlakySMTP)
    report = send_emails(_contacts(), settings=_settings())
    assert report.sent == ["alice@example.com"]
    assert report.failed == [("bob@example.com", "connection reset")]
    assert not report.ok


def test_send_emails_dry_run_never_connects() -> None:
    report = send_emails(_contacts(), settings=_settings(), dry_run=True)
    assert report.dry_run
    assert report.sent == ["alice@example.com", "bob@example.com"]
    assert not FakeSMTP.instances


def test_send_emails_requires_host_without_dry_run() -> None:
    settings = Settings(_env_file=None)
    with pytest.raises(MailError, match="SMTP_HOST"):
        send_emails(_contacts(), settings=settings)


def test_connection_failure_raises_mail_error(monkeypatch) -> None:
    class BrokenSMTP(FakeSMTP):
        def __init__(self, host: str, port: int = 0, timeout: float = 0) -> None:
            raise OSError("refused")

    monkeypatch.setattr("linkdogger.mail.sender.smtplib.SMTP", BrokenSMTP)
    with pytest.raises(MailError, match="could not connect"):
        send_emails(_contacts(), settings=_settings())


def test_defaults_render_all_placeholders() -> None:
    message = build_message(
        Contact(email="bob@example.com", name="Bob", company="Acme"),
        DEFAULT_SUBJECT,
        DEFAULT_BODY,
        _settings(),
    )
    assert "{name}" not in message["Subject"]
    assert "{name}" not in message.get_content()


def test_validate_email_normalizes_and_rejects() -> None:
    assert validate_email("  Alice@Example.COM ") == "alice@example.com"
    assert validate_email("not-an-email") is None
    assert validate_email("a@b@c.com") is None
    assert validate_email("x@y.com\r\nBcc: z@y.com") is None


def test_send_test_email_delivers_single_message() -> None:
    report = send_test_email(
        "me@example.com",
        "Test title",
        "Test body",
        settings=_settings(),
    )
    assert report.total == 1
    assert report.sent == ["me@example.com"]
    smtp = FakeSMTP.instances[0]
    assert len(smtp.messages) == 1
    assert smtp.messages[0]["Subject"] == "Test title"
    assert "Test body" in smtp.messages[0].get_content()


def test_send_test_email_dry_run_never_connects() -> None:
    report = send_test_email(
        "me@example.com",
        "Test title",
        "Test body",
        settings=_settings(),
        dry_run=True,
    )
    assert report.sent == ["me@example.com"]
    assert not FakeSMTP.instances


def test_send_generated_delivers_per_contact_drafts() -> None:
    drafts = [("For Alice", "Body A"), ("For Bob", "Body B")]
    report = send_generated(_contacts(), drafts, settings=_settings())
    assert report.total == 2
    assert report.sent == ["alice@example.com", "bob@example.com"]
    smtp = FakeSMTP.instances[0]
    assert [m["Subject"] for m in smtp.messages] == ["For Alice", "For Bob"]
    assert "Body B" in smtp.messages[1].get_content()


def test_send_generated_requires_matching_drafts() -> None:
    with pytest.raises(MailError, match="drafts"):
        send_generated(_contacts(), [("only", "one")], settings=_settings())


def test_send_generated_dry_run_builds_without_connecting() -> None:
    drafts = [("For Alice", "Body A"), ("For Bob", "Body B")]
    report = send_generated(_contacts(), drafts, settings=_settings(), dry_run=True)
    assert report.sent == ["alice@example.com", "bob@example.com"]
    assert not FakeSMTP.instances
