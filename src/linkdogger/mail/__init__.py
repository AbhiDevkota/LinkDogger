"""Email sending (SMTP outbox) and reply watching (IMAP observer)."""

from linkdogger.mail.contacts import Contact, load_contacts, validate_email
from linkdogger.mail.observer import (
    ReplyObserver,
    ReplyRecord,
    build_reply_report,
    observe_replies,
)
from linkdogger.mail.sender import (
    DEFAULT_BODY,
    DEFAULT_SUBJECT,
    SendReport,
    build_message,
    send_emails,
    send_emails_from_file,
    send_test_email,
)

__all__ = [
    "Contact",
    "DEFAULT_BODY",
    "DEFAULT_SUBJECT",
    "ReplyObserver",
    "ReplyRecord",
    "SendReport",
    "build_message",
    "build_reply_report",
    "load_contacts",
    "observe_replies",
    "send_emails",
    "send_emails_from_file",
    "send_test_email",
    "validate_email",
]
