"""Mock discovery behavior."""

from linkdogger.discovery.mock import MOCK_SOURCE, MockPeopleDiscoverer


def test_known_company_returns_sample_people() -> None:
    people = MockPeopleDiscoverer().discover_people("Acme")
    assert len(people) > 0
    assert all(person.company == "Acme" for person in people)


def test_known_company_match_is_case_insensitive() -> None:
    people = MockPeopleDiscoverer().discover_people("OPENAI")
    assert len(people) > 0


def test_unknown_company_returns_nothing() -> None:
    assert MockPeopleDiscoverer().discover_people("Mystery Inc") == []


def test_sample_sources_are_marked_as_mock() -> None:
    people = MockPeopleDiscoverer().discover_people("Acme")
    assert all(MOCK_SOURCE in person.sources for person in people)
    assert all(
        profile.source == MOCK_SOURCE
        for person in people
        for profile in person.profiles.values()
    )
