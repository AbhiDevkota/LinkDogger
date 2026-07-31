"""Application core service.

Shared by the CLI and (later) the web GUI so no business logic is
duplicated across interfaces. The architecture keeps a persistent
store optional: a database can be added behind this service without
changing its callers.
"""

from datetime import UTC, datetime

from linkdogger.discovery.base import PeopleDiscoverer
from linkdogger.models.search import SearchResult


class PeopleService:
    """Orchestrates discovery into a structured search result."""

    def __init__(self, discoverer: PeopleDiscoverer) -> None:
        self._discoverer = discoverer

    def search_company(self, company: str) -> SearchResult:
        """Discover publicly discoverable people for ``company``."""
        people = list(self._discoverer.discover_people(company))
        return SearchResult(
            query=company,
            generated_at=datetime.now(UTC),
            count=len(people),
            results=people,
        )
