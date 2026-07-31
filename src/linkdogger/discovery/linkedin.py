"""LinkedIn discovery.

LinkedIn offers no official public API without authentication. LinkDogger's
LinkedIn provider uses the optional ``open-linkedin-api`` library (a
synchronous client for LinkedIn's Voyager API) with your own account
credentials. Everything stays opt-in: no credentials means no LinkedIn
access, and no data is ever guessed or fabricated.

With credentials the provider can now do full LinkedIn discovery:

* companies resolve through ``search_companies`` (the real company name
  and its URN id, which people search filters on);
* people are discovered through ``search_people``, filtered to the
  company's URN id when available (the library respects LinkedIn's rate
  limits by sleeping between requests).

Without credentials, company resolution falls back to the slug-derived
URL (honestly marked ``linkedin-slug``) and people discovery reports
``unavailable`` instead of fabricating profiles.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from linkdogger.config.settings import Settings
from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.errors import SourceUnavailableError
from linkdogger.linkedin_api import get_linkedin_client
from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

logger = logging.getLogger(__name__)

COMPANY_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

SOURCE = "linkedin-api"


def _company_slug(query: str) -> str:
    """Best-effort LinkedIn company slug from a plain-text query."""
    slug = COMPANY_SLUG_PATTERN.sub("-", query.strip().lower()).strip("-")
    return slug


class LinkedInCompanyDiscoverer(CompanyDiscoverer):
    """Resolves companies to LinkedIn company pages.

    With credentials, ``search_companies`` finds the real company
    (including its URN id, which people search uses as a filter);
    without credentials — or when the API fails — the slug-derived URL
    is used as-is, honestly marked with the ``linkedin-slug`` source.
    """

    def __init__(self, settings: Settings) -> None:
        self._email = settings.linkedin_email
        self._password = settings.linkedin_password
        self._cookies_dir = settings.linkedin_cookies_dir
        self._cookie_file = settings.linkedin_cookie_file
        self._timeout = settings.request_timeout_seconds

    def resolve_company(self, query: str) -> Company | None:
        if not query.strip():
            return None
        slug = _company_slug(query)
        if not slug:
            return None

        client = self._client_or_none()
        if client is not None:
            resolved = self._resolve_with_api(client, query, slug)
            if resolved is not None:
                return resolved

        logger.info("LinkedIn company URL (slug, unverified): %s", slug)
        return Company(
            name=query.strip(),
            aliases=[slug],
            source="linkedin-slug",
            resolved_from=query,
        )

    def _client_or_none(self) -> Any | None:
        try:
            return get_linkedin_client(
                self._email,
                self._password,
                self._cookies_dir,
                self._cookie_file,
                timeout=self._timeout,
            )
        except SourceUnavailableError as exc:
            logger.info("LinkedIn API unavailable; using slug fallback: %s", exc)
            return None

    def _resolve_with_api(self, client: Any, query: str, slug: str) -> Company | None:
        try:
            # Bound the search: we only need the first hit. The library
            # pages until an empty result when no limit is given, which
            # with common queries means dozens of requests (each with a
            # 2-5 s sleep) for results we would throw away.
            results = client.search_companies(keywords=[query], limit=5)
            if results:
                first = results[0]
                aliases: list[str] = [slug]
                if first.get("urn_id"):
                    aliases.insert(0, first["urn_id"])
                return Company(
                    name=first.get("name") or query.strip(),
                    aliases=aliases,
                    description=first.get("headline") or first.get("subline"),
                    source=SOURCE,
                    resolved_from=query,
                )
            company = client.get_company(slug)
            if company:
                return Company(
                    name=company.get("name") or query.strip(),
                    aliases=[slug],
                    description=company.get("description"),
                    source=SOURCE,
                    resolved_from=query,
                )
        except Exception as exc:  # noqa: BLE001 - search failures are varied
            logger.warning("LinkedIn company resolution failed: %s", exc)
        return None


class LinkedInPeopleDiscoverer(PeopleDiscoverer):
    """Discovers people at a company through LinkedIn's people search.

    Without credentials this source honestly reports ``unavailable``
    (the previous behavior) instead of guessing.
    """

    def __init__(self, settings: Settings) -> None:
        self._email = settings.linkedin_email
        self._password = settings.linkedin_password
        self._cookies_dir = settings.linkedin_cookies_dir
        self._cookie_file = settings.linkedin_cookie_file
        self._limit = settings.max_results
        self._timeout = settings.request_timeout_seconds

    def discover_people(self, company: Company) -> list[PersonProfile]:
        client = get_linkedin_client(
            self._email,
            self._password,
            self._cookies_dir,
            self._cookie_file,
            timeout=self._timeout,
        )
        try:
            results = self._search(client, company)
        except SourceUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - search failures are varied
            raise SourceUnavailableError(
                f"LinkedIn people search failed: {exc}"
            ) from exc
        people = []
        for item in results:
            name = item.get("name")
            if not name:
                continue
            username = item.get("urn_id")
            people.append(
                PersonProfile(
                    name=name,
                    position=item.get("jobtitle"),
                    location=item.get("location"),
                    profiles={
                        "linkedin": SocialProfile(
                            platform="linkedin",
                            url=None,
                            username=username,
                            source=SOURCE,
                            confidence=0.7,
                        )
                    },
                    sources=[SOURCE],
                )
            )
        logger.info("LinkedIn people search returned %d profile(s)", len(people))
        return people

    def _search(self, client: Any, company: Company) -> list[dict[str, Any]]:
        urn_id = _company_urn_id(company)
        if urn_id is not None:
            return client.search_people(current_company=[urn_id], limit=self._limit)
        return client.search_people(keywords=company.name, limit=self._limit)


def _company_urn_id(company: Company) -> str | None:
    """The URN id from resolved companies (first alias, when numeric)."""
    for alias in company.aliases:
        if alias.isdigit():
            return alias
    return None
