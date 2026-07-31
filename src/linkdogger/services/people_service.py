"""Application core service.

Shared by the CLI and the web GUI so no business logic is duplicated
across interfaces. The architecture keeps a persistent store optional:
a database can be added behind this service without changing callers.
"""

import logging
from datetime import UTC, datetime

from linkdogger.config.settings import Settings
from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.errors import LinkDoggerError, RateLimitError
from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SearchResult

logger = logging.getLogger(__name__)


class PeopleService:
    """Orchestrates discovery into a structured search result."""

    def __init__(
        self,
        settings: Settings,
        company_discoverer: CompanyDiscoverer,
        people_discoverer: PeopleDiscoverer,
    ) -> None:
        self._settings = settings
        self._company_discoverer = company_discoverer
        self._people_discoverer = people_discoverer

    def search_company(self, company_query: str) -> SearchResult:
        """Discover publicly discoverable people for ``company_query``."""
        logger.info("Searching company: %s", company_query)
        company = self._resolve_company(company_query)
        if company is None:
            logger.info("Company not found: %s", company_query)
            return self._empty_result(company_query)

        logger.info("Resolved company: %s", company.name)
        people = self._discover_people(company)
        logger.info("Found %d candidate profiles", len(people))

        return SearchResult(
            query=company_query,
            generated_at=datetime.now(UTC),
            count=len(people),
            company=company,
            results=people,
            source_status={},
            warnings=[],
        )

    def _resolve_company(self, company_query: str) -> Company | None:
        try:
            return self._company_discoverer.resolve_company(company_query)
        except RateLimitError as exc:
            logger.warning("Company resolution rate limited: %s", exc)
            return None
        except LinkDoggerError as exc:
            logger.warning("Company resolution failed: %s", exc)
            return None

    def _discover_people(self, company: Company) -> list[PersonProfile]:
        try:
            return list(self._people_discoverer.discover_people(company.name))
        except RateLimitError as exc:
            logger.warning("People discovery rate limited: %s", exc)
            return []
        except LinkDoggerError as exc:
            logger.warning("People discovery failed: %s", exc)
            return []

    def _empty_result(self, company_query: str) -> SearchResult:
        return SearchResult(
            query=company_query,
            generated_at=datetime.now(UTC),
            count=0,
            company=None,
            results=[],
            source_status={},
            warnings=[],
        )
