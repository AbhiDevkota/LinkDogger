"""Application core service.

Shared by the CLI and the web GUI so no business logic is duplicated
across interfaces. The architecture keeps a persistent store optional:
a database can be added behind this service without changing callers.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from linkdogger.config.settings import Settings
from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.enrichment.base import Enricher
from linkdogger.errors import (
    EnrichmentIncompleteError,
    LinkDoggerError,
    RateLimitError,
    SourceUnavailableError,
)
from linkdogger.matching.identity import IdentityMatcher
from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SearchResult
from linkdogger.scoring.networking import NetworkingScorer

logger = logging.getLogger(__name__)

KNOWN_PLATFORMS = ("linkedin", "github", "x", "website")


class PeopleService:
    """Orchestrates the search pipeline:

    resolve company -> discover people -> enrich profiles ->
    source status -> structured result.
    """

    def __init__(
        self,
        settings: Settings,
        company_discoverer: CompanyDiscoverer,
        people_discoverer: PeopleDiscoverer,
        enrichers: Sequence[Enricher] = (),
        identity_matcher: IdentityMatcher | None = None,
        networking_scorer: NetworkingScorer | None = None,
    ) -> None:
        self._settings = settings
        self._company_discoverer = company_discoverer
        self._people_discoverer = people_discoverer
        self._enrichers = list(enrichers)
        self._identity_matcher = identity_matcher or IdentityMatcher()
        self._networking_scorer = networking_scorer or NetworkingScorer()

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

        people, source_status = self._enrich_people(people)
        logger.info("Enrichment complete for %d people", len(people))

        people = self._match_people(people)
        logger.info("Identity matching complete: %d people", len(people))

        people = self._score_people(people)
        logger.info("Networking scores calculated for %d people", len(people))

        return SearchResult(
            query=company_query,
            generated_at=datetime.now(UTC),
            count=len(people),
            company=company,
            results=people,
            source_status=source_status,
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
            return list(self._people_discoverer.discover_people(company))
        except RateLimitError as exc:
            logger.warning("People discovery rate limited: %s", exc)
            return []
        except LinkDoggerError as exc:
            logger.warning("People discovery failed: %s", exc)
            return []

    def _enrich_people(
        self,
        people: list[PersonProfile],
    ) -> tuple[list[PersonProfile], dict[str, str]]:
        """Run all enrichers; one failing source never destroys the search."""
        statuses = self._initial_statuses(people)
        for enricher in self._enrichers:
            try:
                people = enricher.enrich_all(people)
                statuses[enricher.name] = "ok"
            except EnrichmentIncompleteError as exc:
                statuses[enricher.name] = "partial"
                logger.warning("Source %s: %s", enricher.name, exc)
            except SourceUnavailableError as exc:
                statuses[enricher.name] = "unavailable"
                logger.info("Source %s unavailable: %s", enricher.name, exc)
            except LinkDoggerError as exc:
                statuses[enricher.name] = "error"
                logger.warning("Source %s failed: %s", enricher.name, exc)
            except Exception:
                statuses[enricher.name] = "error"
                logger.exception("Unexpected error in source %s", enricher.name)
        return people, statuses

    @staticmethod
    def _initial_statuses(people: Sequence[PersonProfile]) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for platform in KNOWN_PLATFORMS:
            found = any(platform in person.profiles for person in people)
            statuses[platform] = "ok" if found else "no-data"
        return statuses

    def _match_people(self, people: list[PersonProfile]) -> list[PersonProfile]:
        return self._identity_matcher.match_people(people)

    def _score_people(self, people: list[PersonProfile]) -> list[PersonProfile]:
        for person in people:
            person.networking = self._networking_scorer.score(person)
        return people

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
