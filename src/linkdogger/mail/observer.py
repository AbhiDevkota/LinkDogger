"""Reply observer — watches the inbox for replies from sent contacts.

SMTP can only send; replies land in your mailbox, so this module polls
an IMAP inbox and matches inbound messages against the contacts you
wrote to (by ``From`` address). Every match is reported so the user
knows who answered, what they said and when. Implements the "observe"
half of the outreach loop: send → watch → report.
"""

from __future__ import annotations

import contextlib
import email
import imaplib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from typing import ClassVar

from linkdogger.config.settings import Settings
from linkdogger.errors import MailError
from linkdogger.mail.contacts import Contact

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplyRecord:
    """One inbound reply from a watched contact."""

    uid: str
    sender: str
    sender_name: str | None
    subject: str
    date: str | None
    preview: str


class ReplyObserver:
    """Scans an IMAP inbox for replies from a set of contacts."""

    PREVIEW_LIMIT: ClassVar[int] = 240

    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._settings = settings or Settings()
        self._timeout = timeout

    def scan(
        self,
        contacts: list[Contact],
        folder: str | None = None,
        since_days: int | None = 7,
    ) -> list[ReplyRecord]:
        """Fetch inbox messages and keep the ones from ``contacts``.

        ``since_days`` limits the search window (``None`` searches the
        whole folder). Returns matches ordered by IMAP sequence number.
        """
        if not self._settings.imap_host:
            raise MailError("LINKDOGGER_IMAP_HOST is not set")
        watched = {contact.email.lower() for contact in contacts}
        if not watched:
            raise MailError("no email addresses to watch")

        imap = self._connect()
        try:
            imap.select(self._settings.imap_folder if folder is None else folder)
            uids = self._search(imap, since_days)
            records: list[ReplyRecord] = []
            for uid in uids:
                record = self._fetch_and_match(imap, uid, watched)
                if record is not None:
                    records.append(record)
            return records
        finally:
            with contextlib.suppress(imaplib.IMAP4.error, OSError):
                imap.logout()

    def _connect(self) -> imaplib.IMAP4:
        host = self._settings.imap_host
        assert host is not None
        try:
            if self._settings.imap_starttls:
                imap = imaplib.IMAP4(host, self._settings.imap_port, self._timeout)
                imap.starttls()
            else:
                imap = imaplib.IMAP4_SSL(
                    host, self._settings.imap_port, timeout=self._timeout
                )
            imap.login(
                self._settings.imap_username or "",
                self._settings.imap_password or "",
            )
            return imap
        except (imaplib.IMAP4.error, OSError) as exc:
            raise MailError(f"could not connect to IMAP server {host}: {exc}") from exc

    @staticmethod
    def _search(imap: imaplib.IMAP4, since_days: int | None) -> list[bytes]:
        if since_days is not None:
            since = (datetime.now(UTC) - timedelta(days=since_days)).date()
            criteria = f'(SINCE "{since.strftime("%d-%b-%Y")}")'
        else:
            criteria = "ALL"
        status, data = imap.uid("SEARCH", criteria)
        if status != "OK":
            raise MailError("IMAP search failed")
        return (data[0] or b"").split()

    def _fetch_and_match(
        self, imap: imaplib.IMAP4, uid: bytes, watched: set[str]
    ) -> ReplyRecord | None:
        uid_text = uid.decode("ascii", errors="replace")
        status, data = imap.uid("FETCH", uid_text, "(RFC822)")
        if status != "OK" or not data:
            return None
        raw = _extract_raw_message(data)
        if raw is None:
            return None
        message = email.message_from_bytes(raw)
        _, sender = parseaddr(message.get("From", ""))
        if sender.lower() not in watched:
            return None
        return ReplyRecord(
            uid=uid_text,
            sender=sender.lower(),
            sender_name=parseaddr(message.get("From", ""))[0] or None,
            subject=str(message.get("Subject", "")),
            date=str(message.get("Date", "")).strip() or None,
            preview=_preview(_body_text(message), self.PREVIEW_LIMIT),
        )


def _extract_raw_message(data: list) -> bytes | None:
    """Pull the RFC822 bytes out of an IMAP FETCH response."""
    for item in data:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _body_text(message: email.message.Message) -> str:
    for part in message.walk():
        if part.get_content_type() == "text/plain":
            return _decode_payload(part)
    for part in message.walk():
        if part.get_content_type() == "text/html":
            return _strip_html(_decode_payload(part))
    return _decode_payload(message)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def _decode_payload(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _preview(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:limit] + ("…" if len(collapsed) > limit else "")


def build_reply_report(replies: list[ReplyRecord], contacts: list[Contact]) -> dict:
    """JSON-friendly summary of what the observer found."""
    watched = {contact.email.lower() for contact in contacts}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "watched": sorted(watched),
        "count": len(replies),
        "replies": [
            {
                "sender": reply.sender,
                "sender_name": reply.sender_name,
                "subject": reply.subject,
                "date": reply.date,
                "preview": reply.preview,
            }
            for reply in replies
        ],
    }


def observe_replies(
    contacts: list[Contact],
    settings: Settings | None = None,
    folder: str | None = None,
    since_days: int | None = 7,
) -> list[ReplyRecord]:
    """One-shot convenience scan (see ``ReplyObserver.scan``)."""
    return ReplyObserver(settings).scan(contacts, folder=folder, since_days=since_days)
