"""LinkedIn enrichment via the optional ``linkedin-scraper`` library.

``linkedin-scraper`` is a Playwright-based scraper (v3+): it opens a
real browser using your own authenticated LinkedIn session and reads
profile pages. LinkDogger therefore treats LinkedIn as an *opt-in
extraction engine*:

* the session is created once, by you (``linkdogger linkedin-login``),
  in your own browser and saved for reuse;
* the session file is reused (``load_session``) and never shared;
* nothing is scraped unless a person already has a known LinkedIn URL
  (e.g. found in a public GitHub bio);
* rate limits are respected with a delay between requests and never
  circumvented; ``RateLimitError`` propagates instead of retrying hard.

The browser is launched with anti-detection options (real Chrome
channel, automation flag disabled, ``navigator.webdriver`` hidden).
These are legitimate usability options so your own logged-in session
works — not CAPTCHA bypass or rate-limit evasion.

Without the library or a session file this source honestly reports
``unavailable`` instead of guessing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from linkdogger.config.settings import Settings
from linkdogger.errors import (
    EnrichmentIncompleteError,
    RateLimitError,
    SourceUnavailableError,
)
from linkdogger.models.person import PersonProfile

logger = logging.getLogger(__name__)

SCRAPE_DELAY_SECONDS = 2.0
NOT_INSTALLED_MESSAGE = (
    "linkedin-scraper is not installed; install it with "
    "`pip install -e '.[linkedin]'` (and `playwright install chromium`)"
)
NO_SESSION_MESSAGE = (
    "LinkedIn session file not configured; set LINKDOGGER_LINKEDIN_SESSION_FILE "
    "and create the session with `linkdogger linkedin-login`"
)
WEBDRIVER_HIDE_SCRIPT = """
Object.defineProperty(navigator, "webdriver", { get: () => undefined });
"""


def linkedin_launch_options() -> dict[str, object]:
    """Playwright launch options that reduce LinkedIn bot detection.

    Uses the real installed Chrome (``channel="chrome"``) instead of the
    bundled Chromium and disables the automation-controlled flag so the
    browser behaves like a normal human session. These are legitimate
    usability options — not CAPTCHA bypass or rate-limit evasion.
    """
    return {
        "channel": "chrome",
        "args": ["--disable-blink-features=AutomationControlled"],
    }


async def hide_automation_flags(manager: object) -> None:
    """Hide ``navigator.webdriver`` on the live browser context.

    ``load_session`` recreates the browser context, so this must run
    after the session is loaded, on the live context.
    """
    context = getattr(manager, "context", None)
    add_init_script = getattr(context, "add_init_script", None)
    if add_init_script is not None:
        try:
            await add_init_script(WEBDRIVER_HIDE_SCRIPT)
        except Exception as exc:  # noqa: BLE001 - best-effort anti-detection
            logger.debug("Could not hide automation flags: %s", exc)


class LinkedInEnricher:
    """Enriches people who already have a LinkedIn URL using the scraper."""

    name = "linkedin"

    def __init__(self, settings: Settings | None = None) -> None:
        self._session_file = settings.linkedin_session_file if settings else None
        self._headless = settings.linkedin_headless if settings else True

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        targets = [p for p in people if self._linkedin_url(p) is not None]
        if not targets:
            return list(people)

        try:
            import linkedin_scraper  # noqa: F401 - availability check
        except ImportError as exc:
            raise SourceUnavailableError(NOT_INSTALLED_MESSAGE) from exc

        session_file = self._session_file
        if not session_file or not Path(session_file).is_file():
            raise SourceUnavailableError(NO_SESSION_MESSAGE)

        try:
            return asyncio.run(self._scrape(list(people), session_file))
        except (EnrichmentIncompleteError, SourceUnavailableError, RateLimitError):
            raise
        except Exception as exc:  # noqa: BLE001 - browser failures are varied
            logger.warning("LinkedIn enrichment failed: %s", exc)
            raise SourceUnavailableError(f"LinkedIn enrichment failed: {exc}") from exc

    @staticmethod
    def _linkedin_url(person: PersonProfile) -> str | None:
        profile = person.profiles.get("linkedin")
        if profile and profile.url:
            return profile.url
        return None

    async def _scrape(
        self, people: list[PersonProfile], session_file: str
    ) -> list[PersonProfile]:
        import linkedin_scraper

        try:
            manager = linkedin_scraper.BrowserManager(
                headless=self._headless, **linkedin_launch_options()
            )
            async with manager:
                return await self._scrape_with(manager, people)
        except Exception as exc:  # noqa: BLE001 - launch failure (e.g. no Chrome)
            if "Failed to start browser" not in str(exc):
                raise
            logger.warning("Chrome launch failed (%s); falling back to Chromium", exc)
            manager = linkedin_scraper.BrowserManager(headless=self._headless)
            async with manager:
                return await self._scrape_with(manager, people)

    async def _scrape_with(
        self, browser_manager: Any, people: list[PersonProfile]
    ) -> list[PersonProfile]:
        import linkedin_scraper

        skipped = 0
        await browser_manager.load_session(self._session_file)
        await hide_automation_flags(browser_manager)
        scraper = linkedin_scraper.PersonScraper(browser_manager.page)
        for person in people:
            url = self._linkedin_url(person)
            if url is None:
                continue
            try:
                scraped = await scraper.scrape(url)
                self._apply_person_data(person, scraped)
            except linkedin_scraper.AuthenticationError as exc:
                raise SourceUnavailableError(
                    "LinkedIn session expired; re-run `linkdogger linkedin-login`"
                ) from exc
            except linkedin_scraper.RateLimitError as exc:
                raise RateLimitError("LinkedIn rate limit reached") from exc
            except linkedin_scraper.ProfileNotFoundError:
                logger.info("LinkedIn profile not found or private: %s", url)
                skipped += 1
            except Exception as exc:  # noqa: BLE001 - per-person isolation
                logger.warning("LinkedIn scrape failed for %s: %s", url, exc)
                skipped += 1
            await asyncio.sleep(SCRAPE_DELAY_SECONDS)
        if skipped:
            raise EnrichmentIncompleteError(
                f"LinkedIn skipped {skipped} profile(s) (not found or failed)",
                skipped,
            )
        return people

    def _apply_person_data(self, person: PersonProfile, scraped: object) -> None:
        """Copy scraped data into the profile without overwriting known data."""
        name = getattr(scraped, "name", None)
        headline = getattr(scraped, "headline", None)
        location = getattr(scraped, "location", None)
        about = getattr(scraped, "about", None)
        if name and not person.name:
            person.name = name
        if headline and not person.position:
            person.position = headline
        if location and not person.location:
            person.location = location
        if about and not person.bio:
            person.bio = about
        if "linkedin-scraper" not in person.sources:
            person.sources.append("linkedin-scraper")
