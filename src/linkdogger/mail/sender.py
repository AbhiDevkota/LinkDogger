"""SMTP outbox — send personalized outreach emails to exported contacts.

Uses only the standard library (``smtplib`` + ``email.message``).
Recipients come from a contacts file (see ``linkdogger.mail.contacts``);
each message is personalized by substituting ``{name}``, ``{company}``,
``{position}`` and ``{from_name}`` in the subject and body. Failures
are isolated per recipient: one bad address never aborts the batch.
"""

from __future__ import annotations

import contextlib
import logging
import smtplib
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from linkdogger.config.settings import Settings
from linkdogger.errors import MailError
from linkdogger.mail.contacts import Contact, load_contacts

logger = logging.getLogger(__name__)

DEFAULT_SUBJECT = "Hello {name} — a quick question"
DEFAULT_BODY = (
    "Hi {name},\n\n"
    "I came across your public profile while researching {company} and "
    "wanted to reach out. I'd love to connect and learn a little more "
    "about your work.\n\n"
    "Best regards,\n{from_name}"
)

PLACEHOLDERS = ("name", "company", "position", "from_name")


@dataclass
class SendReport:
    """Outcome of a send batch."""

    total: int
    sent: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return not self.failed


def send_emails(
    contacts: list[Contact],
    subject: str = DEFAULT_SUBJECT,
    body: str = DEFAULT_BODY,
    settings: Settings | None = None,
    dry_run: bool = False,
    delay_seconds: float = 1.0,
) -> SendReport:
    """Send one personalized email per contact.

    With ``dry_run`` no connection is made — messages are built and
    reported so the template can be reviewed first. A connection-level
    failure raises ``MailError``; individual delivery failures are
    collected in the report.
    """
    settings = settings or Settings()
    recipients = [(contact, subject, body) for contact in contacts]
    return _send(recipients, settings, dry_run, delay_seconds)


def send_generated(
    contacts: list[Contact],
    drafts: list[tuple[str, str]],
    settings: Settings | None = None,
    dry_run: bool = False,
    delay_seconds: float = 1.0,
) -> SendReport:
    """Send one email per contact using generated (subject, body) pairs."""
    settings = settings or Settings()
    if len(drafts) != len(contacts):
        raise MailError(f"got {len(drafts)} drafts for {len(contacts)} contacts")
    recipients = [
        (contact, subject, body)
        for contact, (subject, body) in zip(contacts, drafts, strict=True)
    ]
    return _send(recipients, settings, dry_run, delay_seconds)


def _send(
    recipients: list[tuple[Contact, str, str]],
    settings: Settings,
    dry_run: bool,
    delay_seconds: float,
) -> SendReport:
    report = SendReport(total=len(recipients), dry_run=dry_run)

    if not dry_run:
        _require(settings.smtp_host, "LINKDOGGER_SMTP_HOST is not set")

    smtp: smtplib.SMTP | None = None
    try:
        if not dry_run:
            smtp = _connect(settings)
        for contact, subject, body in recipients:
            message = build_message(contact, subject, body, settings)
            if dry_run:
                logger.info("dry-run message for %s", contact.email)
                report.sent.append(contact.email)
                continue
            try:
                assert smtp is not None
                smtp.send_message(message)
                report.sent.append(contact.email)
                logger.info("sent to %s", contact.email)
            except (smtplib.SMTPException, OSError) as exc:
                logger.warning("failed to send to %s: %s", contact.email, exc)
                report.failed.append((contact.email, str(exc)))
            if delay_seconds > 0:
                time.sleep(delay_seconds)
    finally:
        if smtp is not None:
            with contextlib.suppress(smtplib.SMTPException, OSError):
                smtp.quit()
    return report


def build_message(
    contact: Contact,
    subject: str,
    body: str,
    settings: Settings | None = None,
) -> EmailMessage:
    """Build one personalized ``EmailMessage`` for ``contact``."""
    settings = settings or Settings()
    values = {
        "name": contact.name or contact.email,
        "company": contact.company or "",
        "position": contact.position or "",
        "from_name": settings.smtp_from_name or "LinkDogger",
    }
    message = EmailMessage()
    message["Subject"] = _personalize(subject, values)
    message["From"] = _format_from(settings)
    message["To"] = contact.email
    message["Message-ID"] = make_msgid()
    message["X-LinkDogger"] = "1"
    message.set_content(_personalize(body, values))
    return message


def _personalize(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def _format_from(settings: Settings) -> str:
    sender = settings.smtp_from or settings.smtp_username or ""
    if not sender:
        return "LinkDogger"
    if settings.smtp_from_name:
        return formataddr((settings.smtp_from_name, sender))
    return sender


def _connect(settings: Settings) -> smtplib.SMTP:
    host = settings.smtp_host
    assert host is not None
    try:
        smtp = smtplib.SMTP(host, settings.smtp_port, timeout=15)
        smtp.ehlo()
        if settings.smtp_starttls:
            smtp.starttls()
            smtp.ehlo()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        return smtp
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"could not connect to SMTP server {host}: {exc}") from exc


def _require(value: str | None, name: str) -> None:
    if not value:
        raise MailError(name)


def send_emails_from_file(
    path: str,
    subject: str = DEFAULT_SUBJECT,
    body: str = DEFAULT_BODY,
    dry_run: bool = False,
    delay_seconds: float = 1.0,
    settings: Settings | None = None,
) -> SendReport:
    """Convenience: load contacts from ``path`` and send them."""
    contacts = load_contacts(Path(path))
    return send_emails(
        contacts,
        subject=subject,
        body=body,
        settings=settings,
        dry_run=dry_run,
        delay_seconds=delay_seconds,
    )


def send_test_email(
    recipient: str,
    subject: str,
    body: str,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> SendReport:
    """Send one test email to ``recipient`` to verify the SMTP setup."""
    return send_emails(
        [Contact(email=recipient)],
        subject=subject,
        body=body,
        settings=settings,
        dry_run=dry_run,
        delay_seconds=0,
    )
