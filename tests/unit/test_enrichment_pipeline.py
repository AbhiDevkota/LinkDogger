"""Enrichment pipeline behavior in the service layer."""

from linkdogger.config.settings import Settings
from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
from linkdogger.enrichment.linkedin import LinkedInEnricher
from linkdogger.enrichment.social import XEnricher
from linkdogger.services.people_service import PeopleService


def _service_with_unavailable_sources() -> PeopleService:
    return PeopleService(
        Settings(_env_file=None),
        MockCompanyDiscoverer(),
        MockPeopleDiscoverer(),
        enrichers=[LinkedInEnricher(), XEnricher()],
    )


def test_unavailable_sources_do_not_destroy_search() -> None:
    service = _service_with_unavailable_sources()
    result = service.search_company("Acme")
    assert result.count == 3
    assert result.source_status["linkedin"] == "unavailable"
    assert result.source_status["x"] == "unavailable"


def test_source_status_from_mock_profiles() -> None:
    service = PeopleService(
        Settings(_env_file=None),
        MockCompanyDiscoverer(),
        MockPeopleDiscoverer(),
    )
    result = service.search_company("Acme")
    assert result.source_status["linkedin"] == "ok"
    assert result.source_status["github"] == "ok"
    assert result.source_status["x"] == "ok"
    assert result.source_status["website"] == "no-data"
