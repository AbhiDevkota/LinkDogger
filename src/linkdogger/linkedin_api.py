"""Shared helper for the optional ``open-linkedin-api`` integration.

``open-linkedin-api`` is a synchronous HTTP client for LinkedIn's Voyager
API. It can authenticate two ways, both opt-in and using your own
LinkedIn account:

* **session cookies** (``LINKDOGGER_LINKEDIN_COOKIE_FILE``): paste the
  ``li_at`` and ``JSESSIONID`` cookies from your own logged-in browser
  (saved with ``linkdogger linkedin-login``) — useful when password
  login hits a challenge;
* **credentials** (``LINKDOGGER_LINKEDIN_EMAIL`` /
  ``LINKDOGGER_LINKEDIN_PASSWORD``): the library logs in and caches the
  session cookies (``LINKDOGGER_LINKEDIN_COOKIES_DIR``) for reuse.

The library sleeps 2-5 seconds between requests to respect LinkedIn's
rate limits; LinkDogger never attempts to bypass them. Without either
auth method this source honestly reports ``unavailable`` instead of
guessing.

Both the LinkedIn provider's discovery and enrichment use the client
built here so authentication behavior stays in one place.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from linkdogger.errors import SourceUnavailableError

logger = logging.getLogger(__name__)

NOT_INSTALLED_MESSAGE = (
    "open-linkedin-api is not installed; install it with `pip install -e '.[linkedin]'`"
)
NO_CREDENTIALS_MESSAGE = (
    "LinkedIn credentials not configured; set LINKDOGGER_LINKEDIN_EMAIL and "
    "LINKDOGGER_LINKEDIN_PASSWORD, or create a session with "
    "`linkdogger linkedin-login` and set LINKDOGGER_LINKEDIN_COOKIE_FILE "
    "(see .env.example)"
)
COOKIE_FILE_MISSING_MESSAGE = (
    "LinkedIn cookie file not found: %s — create it with "
    "`linkdogger linkedin-login` (or unset LINKDOGGER_LINKEDIN_COOKIE_FILE)"
)
COOKIE_FILE_INVALID_MESSAGE = (
    "LinkedIn cookie file is not valid JSON or is missing li_at/JSESSIONID: "
    "%s — re-run `linkdogger linkedin-login`"
)


def get_linkedin_errors() -> tuple[type[Exception], type[Exception]]:
    """Return ``(ChallengeException, UnauthorizedException)``.

    These are the library's authentication failures; callers catch them
    to distinguish a broken session from a per-profile failure. Raises
    ``SourceUnavailableError`` when the library is missing.
    """
    try:
        from open_linkedin_api.client import (
            ChallengeException,
            UnauthorizedException,
        )
    except ImportError as exc:
        raise SourceUnavailableError(NOT_INSTALLED_MESSAGE) from exc
    return ChallengeException, UnauthorizedException


def get_linkedin_client(
    email: str | None,
    password: str | None,
    cookies_dir: str | None = None,
    cookie_file: str | None = None,
) -> Any:
    """Return an authenticated ``open_linkedin_api.Linkedin`` client.

    A session cookie file (``li_at`` + ``JSESSIONID``, created by
    ``linkdogger linkedin-login``) takes priority; email/password login
    is the fallback. Raises ``SourceUnavailableError`` with an honest
    reason when the library is missing, no auth is configured, or login
    fails.
    """
    try:
        from open_linkedin_api import Linkedin
        from open_linkedin_api.client import (
            ChallengeException,
            UnauthorizedException,
        )
        from open_linkedin_api.cookie_repository import LinkedinSessionExpired
    except ImportError as exc:
        raise SourceUnavailableError(NOT_INSTALLED_MESSAGE) from exc

    if cookie_file:
        cookies = _cookies_from_file(cookie_file)
        logger.info("Using LinkedIn session cookies from %s", cookie_file)
        return Linkedin("", "", cookies=cookies)

    if not email or not password:
        raise SourceUnavailableError(NO_CREDENTIALS_MESSAGE)

    kwargs: dict[str, Any] = {"cookies_dir": cookies_dir or ""}
    try:
        return Linkedin(email, password, **kwargs)
    except LinkedinSessionExpired:
        # Cached cookies expired; the library re-saves them after a fresh
        # login, so force one and keep the cache for next time.
        logger.warning("LinkedIn session cookies expired; logging in again")
        return Linkedin(email, password, refresh_cookies=True, **kwargs)
    except ChallengeException as exc:
        raise SourceUnavailableError(
            f"LinkedIn login challenged ({exc}); check your credentials "
            "in LINKDOGGER_LINKEDIN_EMAIL/LINKDOGGER_LINKEDIN_PASSWORD"
        ) from exc
    except UnauthorizedException as exc:
        raise SourceUnavailableError(
            "LinkedIn rejected the credentials; check "
            "LINKDOGGER_LINKEDIN_EMAIL/LINKDOGGER_LINKEDIN_PASSWORD"
        ) from exc
    except SourceUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001 - login failures are varied
        raise SourceUnavailableError(f"LinkedIn login failed: {exc}") from exc


def _cookies_from_file(path: str) -> Any:
    """Load a ``RequestsCookieJar`` from a ``linkdogger linkedin-login`` file."""
    from requests.cookies import RequestsCookieJar

    file_path = Path(path)
    if not file_path.is_file():
        raise SourceUnavailableError(COOKIE_FILE_MISSING_MESSAGE % path)
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceUnavailableError(COOKIE_FILE_INVALID_MESSAGE % path) from exc
    li_at = data.get("li_at") if isinstance(data, dict) else None
    jsessionid = data.get("JSESSIONID") if isinstance(data, dict) else None
    if not li_at or not jsessionid:
        raise SourceUnavailableError(COOKIE_FILE_INVALID_MESSAGE % path)

    jar = RequestsCookieJar()
    jar.set("li_at", li_at, domain=".linkedin.com", path="/")
    jar.set("JSESSIONID", jsessionid, domain=".linkedin.com", path="/")
    return jar
