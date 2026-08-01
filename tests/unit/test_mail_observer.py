"""IMAP reply observer."""

import email

import pytest

from linkdogger.config.settings import Settings
from linkdogger.errors import MailError
from linkdogger.mail.contacts import Contact
from linkdogger.mail.observer import ReplyObserver, build_reply_report


def _raw_message(
    sender: str, subject: str, body: str, name: str | None = None, html: bool = False
) -> bytes:
    message = email.message.EmailMessage()
    message["From"] = f"{name} <{sender}>" if name else sender
    message["To"] = "outbox@example.com"
    message["Subject"] = subject
    message["Date"] = "Mon, 01 Jan 2026 10:00:00 +0000"
    if html:
        message.add_alternative(f"<html><body>{body}</body></html>", subtype="html")
    else:
        message.set_content(body)
    return message.as_bytes()


class FakeIMAP:
    """In-memory IMAP server with three messages."""

    instances: list["FakeIMAP"] = []

    def __init__(self, host: str, port: int = 993, timeout: float = 15) -> None:
        self.host = host
        self.messages = [
            _raw_message(
                "alice@example.com",
                "Re: quick question",
                "Happy to chat! Pick a time.",
                name="Alice Example",
            ),
            _raw_message(
                "stranger@example.com",
                "Not for you",
                "Ignore me.",
            ),
            _raw_message(
                "bob@example.com",
                "Re: hello",
                "Sorry, too busy this month.",
                html=True,
            ),
        ]
        self.login_credentials: tuple[str, str] | None = None
        self.folder: str | None = None
        self.last_search_criteria: str | None = None
        self.logged_out = False
        FakeIMAP.instances.append(self)

    def login(self, user: str, password: str) -> str:
        self.login_credentials = (user, password)
        return "OK"

    def select(self, folder: str = "INBOX") -> tuple[str, list[bytes]]:
        self.folder = folder
        return ("OK", [b"3"])

    def uid(self, command: str, *args: object) -> tuple[str, list]:
        if command == "SEARCH":
            self.last_search_criteria = str(args[0])
            return ("OK", [b"1 2 3"])
        if command == "FETCH":
            index = int(args[0]) - 1
            raw = self.messages[index]
            header = f"{args[0]} (UID {args[0]} RFC822 {{{len(raw)}}}".encode()
            return ("OK", [(header, raw), b")"])
        return ("BAD", [b"unknown command"])

    def logout(self) -> str:
        self.logged_out = True
        return "BYE"


@pytest.fixture()
def fake_imap(monkeypatch: pytest.MonkeyPatch) -> FakeIMAP:
    FakeIMAP.instances = []
    instance = FakeIMAP("imap.example.com")
    FakeIMAP.instances.append(instance)
    monkeypatch.setattr(
        "linkdogger.mail.observer.imaplib.IMAP4_SSL", lambda *a, **k: instance
    )
    return instance


def _settings(**overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        imap_host="imap.example.com",
        imap_username="outbox@example.com",
        imap_password="hunter2",
        **overrides,
    )


def _contacts() -> list[Contact]:
    return [
        Contact(email="alice@example.com", name="Alice"),
        Contact(email="bob@example.com", name="Bob"),
    ]


def test_scan_returns_only_replies_from_watched_contacts(
    fake_imap: FakeIMAP,
) -> None:
    observer = ReplyObserver(_settings())
    replies = observer.scan(_contacts())
    assert [r.sender for r in replies] == ["alice@example.com", "bob@example.com"]
    assert replies[0].sender_name == "Alice Example"
    assert replies[0].subject == "Re: quick question"
    assert "Happy to chat" in replies[0].preview
    assert fake_imap.login_credentials == ("outbox@example.com", "hunter2")
    assert fake_imap.folder == "INBOX"
    assert fake_imap.logged_out


def test_scan_prefers_plain_text_over_html(fake_imap: FakeIMAP) -> None:
    replies = ReplyObserver(_settings()).scan(_contacts())
    bob = next(r for r in replies if r.sender == "bob@example.com")
    assert "Sorry, too busy this month." in bob.preview


def test_scan_passes_since_criteria(fake_imap: FakeIMAP) -> None:
    ReplyObserver(_settings()).scan(_contacts(), since_days=30)
    assert fake_imap.last_search_criteria is not None
    assert "SINCE" in fake_imap.last_search_criteria


def test_scan_whole_folder_when_no_since(fake_imap: FakeIMAP) -> None:
    ReplyObserver(_settings()).scan(_contacts(), since_days=None)
    assert fake_imap.last_search_criteria == "ALL"


def test_scan_requires_imap_host() -> None:
    with pytest.raises(MailError, match="IMAP_HOST"):
        ReplyObserver(Settings(_env_file=None)).scan(_contacts())


def test_scan_requires_contacts() -> None:
    with pytest.raises(MailError, match="no email addresses"):
        ReplyObserver(_settings()).scan([])


def test_connection_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenIMAP(FakeIMAP):
        def __init__(self, host: str, port: int = 993, timeout: float = 15) -> None:
            raise OSError("connection refused")

    monkeypatch.setattr("linkdogger.mail.observer.imaplib.IMAP4_SSL", BrokenIMAP)
    with pytest.raises(MailError, match="could not connect"):
        ReplyObserver(_settings()).scan(_contacts())


def test_build_reply_report_shape(fake_imap: FakeIMAP) -> None:
    replies = ReplyObserver(_settings()).scan(_contacts())
    report = build_reply_report(replies, _contacts())
    assert report["count"] == 2
    assert report["watched"] == ["alice@example.com", "bob@example.com"]
    assert report["replies"][0]["sender"] == "alice@example.com"
    assert report["replies"][0]["date"] is not None
    assert "generated_at" in report
