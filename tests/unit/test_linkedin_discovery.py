"""LinkedIn discovery behavior."""

import pytest

from linkdogger.config.settings import Settings
from linkdogger.discovery.linkedin import (
    LinkedInCompanyDiscoverer,
    LinkedInPeopleDiscoverer,
)
from linkdogger.errors import SourceUnavailableError
from linkdogger.models.company import Company


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_company_resolved_from_query_slug() -> None:
    discoverer = LinkedInCompanyDiscoverer(_settings())
    company = discoverer.resolve_company("Microsoft")
    assert company is not None
    assert company.name == "Microsoft"
    assert company.aliases == ["microsoft"]
    assert company.source == "linkedin-slug"


def test_company_slug_normalizes_query() -> None:
    discoverer = LinkedInCompanyDiscoverer(_settings())
    company = discoverer.resolve_company("Open AI Inc.")
    assert company is not None
    assert company.aliases == ["open-ai-inc"]


def test_blank_query_returns_none() -> None:
    discoverer = LinkedInCompanyDiscoverer(_settings())
    assert discoverer.resolve_company("   ") is None


def test_people_discovery_reports_unavailable() -> None:
    discoverer = LinkedInPeopleDiscoverer(_settings())
    company = Company(
        name="Acme", aliases=["acme"], source="linkedin-slug", resolved_from="acme"
    )
    with pytest.raises(SourceUnavailableError, match="employee directories"):
        discoverer.discover_people(company)
