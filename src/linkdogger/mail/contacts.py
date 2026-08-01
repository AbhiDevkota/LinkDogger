"""Load email contacts from exported JSON files.

Accepts the document written by ``linkdogger search --export email``
(``emails`` + ``people``), a full search export (``results``), or a
bare JSON list of strings / ``{"email": ...}`` objects. Emails are
validated, de-duplicated and kept in order.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from linkdogger.errors import MailError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

_CRLF_RE = re.compile(r"[\r\n]")


@dataclass(frozen=True)
class Contact:
    """One outreach recipient."""

    email: str
    name: str | None = None
    company: str | None = None
    position: str | None = None


def load_contacts(path: Path) -> list[Contact]:
    """Parse an exported JSON file into validated contacts.

    Raises ``MailError`` for unreadable files or a document with no
    usable email addresses.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MailError(f"could not read '{path}': {exc}") from exc

    entries: list[tuple[str, dict]] = []
    if isinstance(data, dict):
        if "people" in data:
            for person in data["people"]:
                if isinstance(person, dict) and person.get("email"):
                    entries.append((person["email"], person))
        elif "results" in data:
            for person in data["results"]:
                if isinstance(person, dict) and person.get("email"):
                    entries.append((person["email"], person))
        else:
            raise MailError(
                f"'{path}' is not an exported contacts file "
                "(missing 'people' or 'results')"
            )
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                entries.append((item, {}))
            elif isinstance(item, dict) and item.get("email"):
                entries.append((item["email"], item))
            else:
                raise MailError(
                    f"'{path}' contains an entry that is neither an email "
                    "address nor an object with an 'email' key"
                )
    else:
        raise MailError(f"'{path}' does not contain a list or object")

    contacts: list[Contact] = []
    seen: set[str] = set()
    for raw_email, meta in entries:
        email = validate_email(raw_email)
        if not email or email in seen:
            continue
        seen.add(email)
        contacts.append(
            Contact(
                email=email,
                name=meta.get("name") or None,
                company=meta.get("company") or None,
                position=meta.get("position") or None,
            )
        )
    if not contacts:
        raise MailError(f"no valid email addresses found in '{path}'")
    return contacts


def validate_email(value: object) -> str | None:
    """Return the normalized address if ``value`` is a valid email, else None."""
    if not isinstance(value, str):
        return None
    email = value.strip()
    if len(email) > 320 or _CRLF_RE.search(email):
        return None
    if not _EMAIL_RE.match(email):
        return None
    return email.lower()
