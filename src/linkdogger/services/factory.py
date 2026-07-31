"""Service factory — wires the application core from configuration.

Both interfaces (CLI and web) build their ``PeopleService`` here so the
exact same business logic is shared. Provider selection:

* ``linkedin`` (CLI default): LinkedIn company resolution + people
  discovery + profile enrichment through your own LinkedIn account
  (``open-linkedin-api``; credentials via env vars). Without
  credentials, company resolution falls back to slug URLs and people
  discovery honestly reports ``unavailable``.
* ``github``: official GitHub API (public data only, rate limits
  respected).
* ``hybrid``: GitHub discovery + enrichment from both GitHub and
  LinkedIn.
* ``mock`` (web default): clearly marked fictional sample data,
  offline-safe.

The web interface keeps using ``LINKDOGGER_DISCOVERY_BACKEND``
(mock/github) for its backend; the CLI selects a provider explicitly.
"""

import logging

from linkdogger.config.settings import Settings
from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.discovery.github import GitHubCompanyDiscoverer, GitHubPeopleDiscoverer
from linkdogger.discovery.linkedin import (
    LinkedInCompanyDiscoverer,
    LinkedInPeopleDiscoverer,
)
from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
from linkdogger.enrichment.base import Enricher
from linkdogger.enrichment.github import GitHubEnricher
from linkdogger.enrichment.linkedin import LinkedInEnricher
from linkdogger.enrichment.social import XEnricher
from linkdogger.enrichment.website import WebsiteEnricher
from linkdogger.services.people_service import PeopleService

logger = logging.getLogger(__name__)

VALID_PROVIDERS = ("linkedin", "github", "hybrid", "mock")


def build_people_service(
    settings: Settings, provider: str | None = None
) -> PeopleService:
    """Build a ``PeopleService`` from ``settings``.

    ``provider`` defaults to ``settings.discovery_backend`` (used by the
    web interface); the CLI passes an explicit provider.
    """
    provider = provider or settings.discovery_backend
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"unknown provider '{provider}'")

    company_discoverer: CompanyDiscoverer
    people_discoverer: PeopleDiscoverer
    enrichers: list[Enricher]

    if provider == "mock":
        logger.info("Using mock discovery backend (sample data)")
        company_discoverer = MockCompanyDiscoverer()
        people_discoverer = MockPeopleDiscoverer()
        enrichers = []
    elif provider == "github":
        logger.info("Using GitHub provider")
        company_discoverer = GitHubCompanyDiscoverer(settings)
        people_discoverer = GitHubPeopleDiscoverer(settings)
        enrichers = [
            GitHubEnricher(settings),
            WebsiteEnricher(settings),
            XEnricher(),
        ]
    elif provider == "linkedin":
        logger.info("Using LinkedIn provider")
        company_discoverer = LinkedInCompanyDiscoverer(settings)
        people_discoverer = LinkedInPeopleDiscoverer(settings)
        enrichers = [LinkedInEnricher(settings), XEnricher()]
    else:  # hybrid
        logger.info(
            "Using hybrid provider (GitHub discovery + GitHub & LinkedIn enrichment)"
        )
        company_discoverer = GitHubCompanyDiscoverer(settings)
        people_discoverer = GitHubPeopleDiscoverer(settings)
        enrichers = [
            GitHubEnricher(settings),
            LinkedInEnricher(settings),
            WebsiteEnricher(settings),
            XEnricher(),
        ]

    return PeopleService(
        settings=settings,
        company_discoverer=company_discoverer,
        people_discoverer=people_discoverer,
        enrichers=enrichers,
    )
