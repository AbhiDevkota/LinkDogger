"""LinkedIn discovery.

LinkedIn offers no official public API for reading profiles or company
data without authentication. LinkDogger's LinkedIn provider uses the
optional ``linkedin-scraper`` library (a Playwright-based scraper) with a
user-created, authenticated session. Everything stays opt-in: no session
file means no LinkedIn access, and no data is ever guessed or fabricated.

Current capability gap, stated honestly: LinkedIn does not expose an
employee directory to third-party tools, so discovering people purely
from LinkedIn is not possible yet. Use ``--provider github`` or
``--provider hybrid`` for people discovery; LinkedIn is used for
company resolution and profile enrichment.
"""

from __future__ import annotations

import logging
import re

from linkdogger.config.settings import Settings
from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.errors import SourceUnavailableError
from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile

logger = logging.getLogger(__name__)

COMPANY_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _company_slug(query: str) -> str:
    """Best-effort LinkedIn company slug from a plain-text query."""
    slug = COMPANY_SLUG_PATTERN.sub("-", query.strip().lower()).strip("-")
    return slug


class LinkedInCompanyDiscoverer(CompanyDiscoverer):
    """Resolves companies to LinkedIn company pages.

    The LinkedIn URL for a company follows the ``/company/{slug}/``
    pattern. When a session is configured, the page is verified with
    ``CompanyScraper``; without a session the slug is used as-is (the
    resulting URL is marked with an honest ``linkedin-slug`` source).
    """

    def __init__(self, settings: Settings) -> None:
        self._session_file = settings.linkedin_session_file
        self._headless = settings.linkedin_headless

    def resolve_company(self, query: str) -> Company | None:
        if not query.strip():
            return None
        slug = _company_slug(query)
        if not slug:
            return None

        url = f"https://www.linkedin.com/company/{slug}/"
        if self._session_file:
            verified = self._verify_company(url)
            if verified:
                return verified
        logger.info("LinkedIn company URL (slug, unverified): %s", url)
        return Company(
            name=query.strip(),
            aliases=[slug],
            source="linkedin-slug",
            resolved_from=query,
        )

    def _verify_company(self, url: str) -> Company | None:
        try:
            import asyncio

            from linkedin_scraper import CompanyScraper
        except ImportError:
            logger.warning(
                "linkedin-scraper not installed; company URL stays unverified "
                "(install with `pip install -e '.[linkedin]'`)"
            )
            return None

        try:

            async def scrape() -> Company | None:
                from linkedin_scraper import BrowserManager

                from linkdogger.enrichment.linkedin import (
                    hide_automation_flags,
                    linkedin_launch_options,
                )

                async with BrowserManager(
                    headless=self._headless, **linkedin_launch_options()
                ) as browser:
                    await browser.load_session(self._session_file)
                    hide_automation_flags(browser)
                    scraper = CompanyScraper(browser.page)
                    company = await scraper.scrape(url)
                    return Company(
                        name=company.name,
                        aliases=[company.name.lower().replace(" ", "-")],
                        description=getattr(company, "about", None),
                        source="linkedin-scraper",
                        resolved_from=url,
                    )

            return asyncio.run(scrape())
        except SourceUnavailableError as exc:
            logger.warning("LinkedIn company verification unavailable: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001 - scraper raises many error types
            logger.warning("LinkedIn company verification failed: %s", exc)
            return None


class LinkedInPeopleDiscoverer(PeopleDiscoverer):
    """Reports that LinkedIn cannot provide people discovery.

    LinkedIn has no public employee-directory API, and the scraper can
    only read pages you navigate it to. Discovering people purely from
    LinkedIn is therefore not implemented: raising
    ``SourceUnavailableError`` here keeps the search honest instead of
    fabricating or guessing profiles.
    """

    def __init__(self, settings: Settings) -> None:
        self._session_file = settings.linkedin_session_file

    def discover_people(self, company: Company) -> list[PersonProfile]:
        raise SourceUnavailableError(
            "LinkedIn does not expose employee directories to third-party "
            "tools; people discovery from LinkedIn is not available. "
            "Use `--provider github` or `--provider hybrid` to discover "
            "people through public GitHub data."
        )
