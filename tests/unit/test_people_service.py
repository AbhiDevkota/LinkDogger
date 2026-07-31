"""PeopleService orchestration."""

from linkdogger.config.settings import Settings
from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
from linkdogger.services.people_service import PeopleService


def _service() -> PeopleService:
    return PeopleService(
        Settings(_env_file=None),
        MockCompanyDiscoverer(),
        MockPeopleDiscoverer(),
    )


def test_service_returns_structured_result() -> None:
    result = _service().search_company("Acme")
    assert result.query == "Acme"
    assert result.company is not None
    assert result.company.name == "Acme Corporation"
    assert result.count == len(result.results)
    assert result.count > 0
    assert all(person.company == "Acme Corporation" for person in result.results)


def test_service_reports_empty_for_unknown_company() -> None:
    result = _service().search_company("Unknown Co")
    assert result.company is None
    assert result.count == 0
    assert result.results == []


def test_service_handles_blank_query() -> None:
    result = _service().search_company("   ")
    assert result.company is None
    assert result.count == 0
