"""PeopleService failure resilience and limits."""

from collections.abc import Sequence

from linkdogger.config.settings import Settings
from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
from linkdogger.enrichment.base import Enricher
from linkdogger.errors import EnrichmentIncompleteError, ProviderError
from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile
from linkdogger.services.people_service import KNOWN_PLATFORMS, PeopleService
from linkdogger.services.processing import SortKey


def _service(*enrichers: Enricher) -> PeopleService:
    return PeopleService(
        Settings(_env_file=None),
        MockCompanyDiscoverer(),
        MockPeopleDiscoverer(),
        enrichers=enrichers,
    )


class _RaiseEnricher:
    name = "broken-source"

    def __init__(self, error: Exception) -> None:
        self._error = error

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        raise self._error


class _RecordingEnricher:
    name = "recorder"

    def __init__(self) -> None:
        self.seen = 0

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        self.seen = len(people)
        return list(people)


class _BadCompanyDiscoverer:
    def resolve_company(self, company_query: str) -> Company:
        raise ProviderError("provider exploded")


def test_limit_caps_results() -> None:
    result = _service().search_company("Acme", limit=2)
    assert result.count == 2
    assert len(result.results) == 2


def test_limit_stops_enrichment_early() -> None:
    recorder = _RecordingEnricher()
    result = _service(recorder).search_company("Acme", limit=1)
    assert result.count == 1
    assert recorder.seen == 1


def test_sort_ranks_within_limited_candidates() -> None:
    result = _service().search_company(
        "Acme", sort=(SortKey.FOLLOWERS, "desc"), limit=3
    )
    assert result.count == 3
    assert result.results[0].name == "Taylor Sample"


def test_sort_ranks_first_limit_discovered() -> None:
    result = _service().search_company(
        "Acme", sort=(SortKey.FOLLOWERS, "desc"), limit=1
    )
    assert result.count == 1
    assert result.results[0].name == "Alex Sample"


def test_all_known_platforms_report_status() -> None:
    result = _service().search_company("Acme")
    assert set(result.source_status) == set(KNOWN_PLATFORMS)
    assert "github" in result.source_status


def test_failing_enricher_does_not_kill_search() -> None:
    result = _service(_RaiseEnricher(ProviderError("boom"))).search_company("Acme")
    assert result.company is not None
    assert result.count > 0
    assert result.source_status["broken-source"] == "error"


def test_unavailable_enricher_is_marked_not_fatal() -> None:
    from linkdogger.errors import SourceUnavailableError

    result = _service(_RaiseEnricher(SourceUnavailableError("offline"))).search_company(
        "Acme"
    )
    assert result.count > 0
    assert result.source_status["broken-source"] == "unavailable"


def test_partial_enricher_is_marked_partial() -> None:
    error = EnrichmentIncompleteError("skipped", 2)
    result = _service(_RaiseEnricher(error)).search_company("Acme")
    assert result.count > 0
    assert result.source_status["broken-source"] == "partial"


def test_unexpected_enricher_error_is_contained() -> None:
    result = _service(_RaiseEnricher(RuntimeError("unexpected"))).search_company("Acme")
    assert result.count > 0
    assert result.source_status["broken-source"] == "error"


def test_failing_company_discovery_returns_empty_result() -> None:
    service = PeopleService(
        Settings(_env_file=None),
        _BadCompanyDiscoverer(),
        MockPeopleDiscoverer(),
    )
    result = service.search_company("Acme")
    assert result.company is None
    assert result.count == 0
    assert result.results == []


def test_people_discovery_failure_returns_empty_result() -> None:
    class _BadPeopleDiscoverer:
        def discover_people(self, company: Company) -> list[PersonProfile]:
            raise ProviderError("no people")

    service = PeopleService(
        Settings(_env_file=None),
        MockCompanyDiscoverer(),
        _BadPeopleDiscoverer(),
    )
    result = service.search_company("Acme")
    assert result.company is not None
    assert result.count == 0


def test_blank_query_returns_empty_result() -> None:
    result = _service().search_company("   ")
    assert result.company is None
    assert result.count == 0


def test_filters_and_limit_combined() -> None:
    from linkdogger.services.processing import ResultFilters

    result = _service().search_company(
        "Acme", filters=ResultFilters(role="engineer"), limit=5
    )
    assert result.count == 1
    assert result.results[0].position == "Software Engineer"


def test_schema_version_present_on_all_results() -> None:
    assert _service().search_company("Acme").schema_version == "1.0"
    assert _service().search_company("Unknown Co").schema_version == "1.0"
