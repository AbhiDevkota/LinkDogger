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
    timeout: float | None = None,
) -> Any:
    """Return an authenticated ``open_linkedin_api.Linkedin`` client.

    A session cookie file (``li_at`` + ``JSESSIONID``, created by
    ``linkdogger linkedin-login``) takes priority; email/password login
    is the fallback. Raises ``SourceUnavailableError`` with an honest
    reason when the library is missing, no auth is configured, or login
    fails.

    ``timeout`` is injected as a default for the library's HTTP calls —
    the library itself does not set one, so without it a dead connection
    would hang forever.
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
        return _with_session_timeout(Linkedin("", "", cookies=cookies), timeout)

    if not email or not password:
        raise SourceUnavailableError(NO_CREDENTIALS_MESSAGE)

    kwargs: dict[str, Any] = {"cookies_dir": cookies_dir or ""}
    try:
        client = Linkedin(email, password, **kwargs)
    except LinkedinSessionExpired:
        # Cached cookies expired; the library re-saves them after a fresh
        # login, so force one and keep the cache for next time.
        logger.warning("LinkedIn session cookies expired; logging in again")
        client = Linkedin(email, password, refresh_cookies=True, **kwargs)
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
    return _with_session_timeout(client, timeout)


def _with_session_timeout(client: Any, timeout: float | None) -> Any:
    """Give the library's HTTP session a default request timeout.

    ``open-linkedin-api`` never passes ``timeout`` to ``requests``, so a
    stalled connection would block forever. Wrapping ``session.request``
    injects our default while leaving explicit timeouts untouched.
    """
    session = getattr(getattr(client, "client", None), "session", None)
    if session is None or timeout is None:
        return client
    original_request = session.request

    def request(method: str, url: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", timeout)
        return original_request(method, url, **kwargs)

    session.request = request
    return client


def get_profile(
    client: Any, public_id: str | None = None, urn_id: str | None = None
) -> dict[str, Any]:
    """Fetch a LinkedIn profile, best-effort.

    The library's ``get_profile`` calls the legacy Voyager ``profileView``
    endpoint, which LinkedIn has retired (it answers 410) — and the
    library then crashes on the error payload (``KeyError: 'message'``).
    This shim falls back to the Dash ``profiles`` REST endpoint, which
    still answers for member URNs, and returns ``{}`` when neither works.
    Nothing is fabricated.
    """
    try:
        data = client.get_profile(public_id=public_id, urn_id=urn_id)
    except Exception as exc:  # noqa: BLE001 - the library raises on retired endpoints
        challenge_error, unauthorized_error = get_linkedin_errors()
        if isinstance(exc, (challenge_error, unauthorized_error)):
            raise
        data = {}
    if data:
        return data
    return _dash_profile(client, public_id or urn_id)


def _dash_profile(client: Any, identifier: str | None) -> dict[str, Any]:
    """Dash REST profile lookup with a run-level circuit breaker.

    LinkedIn gates the Dash endpoint aggressively (it redirect-loops a
    flagged session), so after the first hard failure we stop trying for
    the rest of the run instead of burning a 2-5 s sleep per person on
    doomed requests.
    """
    if not identifier or getattr(client, "_linkdogger_dash_broken", False):
        return {}
    try:
        res = client._fetch(
            f"/identity/dash/profiles?q=memberIdentity&memberIdentity={identifier}"
        )
        body = res.json() or {}
    except Exception as exc:  # noqa: BLE001 - network/auth failures are varied
        client._linkdogger_dash_broken = True
        logger.warning(
            "LinkedIn profile enrichment unavailable (Dash endpoint blocked: "
            "%s); results carry discovery data only",
            exc,
        )
        return {}
    if res.status_code != 200:
        return {}
    elements = body.get("elements") or []
    if not elements:
        return {}
    return _map_dash_profile(elements[0])


def _map_dash_profile(element: dict[str, Any]) -> dict[str, Any]:
    """Map a Dash profile element onto the keys the enricher consumes."""

    def _text(value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            for key in ("text", "localized"):
                text = value.get(key)
                if isinstance(text, str) and text:
                    return text
        return None

    profile = {
        "firstName": _text(element.get("firstName")),
        "lastName": _text(element.get("lastName")),
        "headline": _text(element.get("headline")),
        "summary": _text(element.get("summary")),
        "locationName": _text(element.get("locationName")),
        "public_id": element.get("publicIdentifier"),
    }
    if not any((profile["firstName"], profile["lastName"], profile["headline"])):
        return {}
    return {key: value for key, value in profile.items() if value is not None}


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
