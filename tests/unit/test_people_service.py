"""PeopleService orchestration."""

from linkdogger.config.settings import Settings
from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
from linkdogger.services.people_service import PeopleService
from linkdogger.services.processing import ResultFilters, SortKey


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


def test_service_defaults_to_followback_descending() -> None:
    result = _service().search_company("Acme")
    likelihoods = [
        person.networking.follow_back_likelihood
        for person in result.results
        if person.networking is not None
    ]
    assert likelihoods == sorted(likelihoods, reverse=True)
    assert result.results[0].name == "Alex Sample"


def test_service_explicit_sort_overrides_default() -> None:
    result = _service().search_company("Acme", sort=(SortKey.NAME, "asc"))
    assert result.results[0].name == "Alex Sample"
    assert [p.name for p in result.results] == sorted([p.name for p in result.results])


def test_service_counts_profiles_excluded_by_filters() -> None:
    result = _service().search_company("Acme", filters=ResultFilters(location="nope"))
    assert result.count == 0
    assert result.filtered_out_count == len(_service().search_company("Acme").results)


def test_service_reports_zero_filtered_without_filters() -> None:
    result = _service().search_company("Acme")
    assert result.filtered_out_count == 0
