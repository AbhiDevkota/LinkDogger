"""GitHub people discovery adapter (official API, mocked transport)."""

import httpx
import pytest

from linkdogger.config.settings import Settings
from linkdogger.discovery.github import GitHubPeopleDiscoverer
from linkdogger.errors import ProviderError, RateLimitError
from linkdogger.models.company import Company

COMPANY = Company(
    name="OpenAI", aliases=["openai"], source="test", resolved_from="OpenAI"
)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, discovery_backend="github", **overrides)


def test_discovers_public_org_members() -> None:
    payload = [
        {"login": "alice-dev", "type": "User"},
        {"login": "bob-coder", "type": "User"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/orgs/openai/members"
        assert "per_page" in request.url.query.decode()
        page = int(request.url.params["page"])
        return httpx.Response(200, json=payload if page == 1 else [])

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
    payload = [
        {"login": "openai", "type": "Organization"},
        {"login": "alice-dev", "type": "User"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, json=payload if page == 1 else [])

    transport = httpx.MockTransport(handler)
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)
    people = discoverer.discover_people(COMPANY)
    assert [p.name for p in people] == ["alice-dev"]


def test_no_members_returns_empty() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)
    assert discoverer.discover_people(COMPANY) == []


def test_company_without_alias_returns_empty() -> None:
    company = Company(name="OpenAI", source="test", resolved_from="OpenAI")
    discoverer = GitHubPeopleDiscoverer(_settings())
    assert discoverer.discover_people(company) == []


def test_paginates_until_empty() -> None:
    page_one = [{"login": f"user{i}", "type": "User"} for i in range(30)]
    page_two = [{"login": "extra-user", "type": "User"}]
    pages = {1: page_one, 2: page_two, 3: []}

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, json=pages[page])

    transport = httpx.MockTransport(handler)
    discoverer = GitHubPeopleDiscoverer(_settings(), transport=transport)
    people = discoverer.discover_people(COMPANY)
    assert len(people) == 31


def test_max_results_caps_members() -> None:
    page_one = [{"login": f"user{i}", "type": "User"} for i in range(30)]
    page_two = [{"login": f"user{i}", "type": "User"} for i in range(30, 60)]

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, json=page_one if page == 1 else page_two)

    discoverer = GitHubPeopleDiscoverer(
        _settings(max_results=45), transport=httpx.MockTransport(handler)
    )
    people = discoverer.discover_people(COMPANY)
    assert len(people) == 45


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
