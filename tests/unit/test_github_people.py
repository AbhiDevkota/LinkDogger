"""GitHub people discovery adapter (official API, mocked transport)."""

import httpx
import pytest

from linkdogger.config.settings import Settings
from linkdogger.discovery.github import GitHubPeopleDiscoverer
from linkdogger.errors import ProviderError, RateLimitError
from linkdogger.models.company import Company

COMPANY = Company(name="OpenAI", source="test", resolved_from="OpenAI")


def _settings() -> Settings:
    return Settings(_env_file=None, discovery_backend="github")


def test_discovers_users_matching_company_field() -> None:
    payload = {
        "total_count": 2,
        "items": [
            {"login": "alice-dev", "type": "User"},
            {"login": "bob-coder", "type": "User"},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "/search/users" in request.url.path
        assert "company" in request.url.query.decode()
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)

    people = discoverer.discover_people(COMPANY)

    assert len(people) == 2
    assert people[0].name == "alice-dev"
    assert people[0].company == "OpenAI"
    assert people[0].profiles["github"].username == "alice-dev"
    assert people[0].profiles["github"].url == "https://github.com/alice-dev"
    assert people[0].sources == ["github-api"]


def test_organizations_are_excluded() -> None:
    payload = {
        "total_count": 1,
        "items": [{"login": "openai", "type": "Organization"}],
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)
    assert discoverer.discover_people(COMPANY) == []


def test_no_matches_returns_empty() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"total_count": 0, "items": []})
    )
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)
    assert discoverer.discover_people(COMPANY) == []


def test_rate_limit_raises_rate_limit_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(403, json={"message": "rate limit exceeded"})
    )
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)
    with pytest.raises(RateLimitError):
        discoverer.discover_people(COMPANY)


def test_malformed_response_raises_provider_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="not json")
    )
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)
    with pytest.raises(ProviderError):
        discoverer.discover_people(COMPANY)
