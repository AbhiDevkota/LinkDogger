"""Service factory — wires the application core from configuration.

Both interfaces (CLI and web) build their ``PeopleService`` here so the
exact same business logic is shared. Backend selection:

* ``mock`` (default): clearly marked fictional sample data, offline-safe.
* ``github``: official GitHub API (public data only, rate limits respected).

The GitHub backend may be combined with a ``LINKDOGGER_GITHUB_TOKEN``
(never committed) to raise rate limits; it is optional.
"""

import logging

from linkdogger.config.settings import Settings
from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.discovery.github import GitHubCompanyDiscoverer
from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
from linkdogger.services.people_service import PeopleService

logger = logging.getLogger(__name__)


def build_people_service(settings: Settings) -> PeopleService:
    """Build a ``PeopleService`` from ``settings``."""
    company_discoverer: CompanyDiscoverer
    people_discoverer: PeopleDiscoverer
    if settings.discovery_backend == "github":
        logger.info("Using GitHub discovery backend")
        company_discoverer = GitHubCompanyDiscoverer(settings)
        people_discoverer = MockPeopleDiscoverer()
    else:
        logger.info("Using mock discovery backend (sample data)")
        company_discoverer = MockCompanyDiscoverer()
        people_discoverer = MockPeopleDiscoverer()

    return PeopleService(
        settings=settings,
        company_discoverer=company_discoverer,
        people_discoverer=people_discoverer,
    )
