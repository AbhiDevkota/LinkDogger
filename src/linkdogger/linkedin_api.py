"""Shared helper for the optional ``open-linkedin-api`` integration.

``open-linkedin-api`` is a synchronous HTTP client for LinkedIn's Voyager
API. It authenticates with your own LinkedIn account credentials and
caches the session cookies, so LinkDogger treats LinkedIn as an *opt-in
source*:

* credentials are provided only by you, via environment variables;
* the library's cookie cache (``LINKDOGGER_LINKEDIN_COOKIES_DIR``) keeps
  the session alive without re-logging in on every run;
* the library sleeps 2-5 seconds between requests to respect LinkedIn's
  rate limits; LinkDogger never attempts to bypass them;
* without credentials this source honestly reports ``unavailable``
  instead of guessing.

Both the LinkedIn provider's discovery and enrichment use the client
built here so authentication behavior stays in one place.
"""

from __future__ import annotations

import logging
from typing import Any

from linkdogger.errors import SourceUnavailableError

logger = logging.getLogger(__name__)

NOT_INSTALLED_MESSAGE = (
    "open-linkedin-api is not installed; install it with `pip install -e '.[linkedin]'`"
)
NO_CREDENTIALS_MESSAGE = (
    "LinkedIn credentials not configured; set LINKDOGGER_LINKEDIN_EMAIL "
    "and LINKDOGGER_LINKEDIN_PASSWORD (see .env.example)"
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
) -> Any:
    """Return an authenticated ``open_linkedin_api.Linkedin`` client.

    Raises ``SourceUnavailableError`` with an honest reason when the
    library is missing, credentials are not configured, or login fails.
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
