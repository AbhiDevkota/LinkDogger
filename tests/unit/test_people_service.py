"""PeopleService orchestration."""

from linkdogger.discovery.mock import MockPeopleDiscoverer
from linkdogger.services.people_service import PeopleService


def test_service_returns_structured_result() -> None:
    service = PeopleService(MockPeopleDiscoverer())
    result = service.search_company("Acme")
    assert result.query == "Acme"
    assert result.count == len(result.results)
    assert result.count > 0
    assert all(person.company == "Acme" for person in result.results)


def test_service_reports_empty_for_unknown_company() -> None:
    service = PeopleService(MockPeopleDiscoverer())
    result = service.search_company("Unknown Co")
    assert result.count == 0
    assert result.results == []


def test_service_handles_blank_query() -> None:
    service = PeopleService(MockPeopleDiscoverer())
    result = service.search_company("   ")
    assert result.count == 0
