"""Mock discovery behavior."""

from linkdogger.discovery.mock import (
    MOCK_SOURCE,
    MockCompanyDiscoverer,
    MockPeopleDiscoverer,
)


def test_mock_company_catalog_resolves_known_queries() -> None:
    company = MockCompanyDiscoverer().resolve_company("OpenAI")
    assert company is not None
    assert company.name == "OpenAI"
    assert company.domain == "openai.com"
    assert company.source == MOCK_SOURCE


def test_mock_company_catalog_resolution_is_case_insensitive() -> None:
    company = MockCompanyDiscoverer().resolve_company("openai")
    assert company is not None
    assert company.name == "OpenAI"


def test_mock_company_catalog_unknown_returns_none() -> None:
    assert MockCompanyDiscoverer().resolve_company("Mystery Inc") is None


def test_mock_people_for_resolved_company() -> None:
    company = MockCompanyDiscoverer().resolve_company("OpenAI")
    assert company is not None
    people = MockPeopleDiscoverer().discover_people(company)
    assert len(people) > 0
    assert all(person.company == "OpenAI" for person in people)


def test_mock_people_blank_company_returns_nothing() -> None:
    company = MockCompanyDiscoverer().resolve_company("OpenAI")
    assert company is not None
    blank = company.model_copy(update={"name": "   "})
    assert MockPeopleDiscoverer().discover_people(blank) == []


def test_sample_sources_are_marked_as_mock() -> None:
    company = MockCompanyDiscoverer().resolve_company("OpenAI")
    assert company is not None
    people = MockPeopleDiscoverer().discover_people(company)
    assert all(MOCK_SOURCE in person.sources for person in people)
    assert all(
        profile.source == MOCK_SOURCE
        for person in people
        for profile in person.profiles.values()
    )
