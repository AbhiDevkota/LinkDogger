"""GitHub company discovery adapter (official API, mocked transport)."""

import httpx
import pytest

from linkdogger.config.settings import Settings
from linkdogger.discovery.github import GitHubCompanyDiscoverer
from linkdogger.errors import ProviderError, RateLimitError


def _settings() -> Settings:
    return Settings(_env_file=None, discovery_backend="github")


def _org_search_payload(login: str = "openai") -> dict:
    return {"total_count": 1, "items": [{"login": login, "type": "Organization"}]}


def _org_payload(name: str = "OpenAI", blog: str = "https://openai.com") -> dict:
    return {
        "login": "openai",
        "name": name,
        "blog": blog,
        "description": "Creating safe AGI",
        "location": "San Francisco",
    }


def _handler(search_payload: dict, org_payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/search/users"):
            return httpx.Response(200, json=search_payload)
        if request.url.path.startswith("/orgs/"):
            return httpx.Response(200, json=org_payload)
        return httpx.Response(404, json={"message": "not found"})

    return handler


def test_resolves_company_via_org_search() -> None:
    transport = httpx.MockTransport(_handler(_org_search_payload(), _org_payload()))
    discoverer = GitHubCompanyDiscoverer(_settings(), transport=transport)

    company = discoverer.resolve_company("OpenAI")

    assert company is not None
    assert company.name == "OpenAI"
    assert company.domain == "openai.com"
    assert company.aliases == ["openai"]
    assert company.source == "github-api"
    assert company.resolved_from == "OpenAI"


def test_no_matching_org_returns_none() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"total_count": 0, "items": []})
    )
    discoverer = GitHubCompanyDiscoverer(_settings(), transport=transport)
    assert discoverer.resolve_company("Unknown Co") is None


def test_rate_limit_raises_rate_limit_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(403, json={"message": "rate limit exceeded"})
    )
    discoverer = GitHubCompanyDiscoverer(_settings(), transport=transport)
    with pytest.raises(RateLimitError):
        discoverer.resolve_company("OpenAI")


def test_malformed_response_raises_provider_error() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="not json")
    )
    discoverer = GitHubCompanyDiscoverer(_settings(), transport=transport)
    with pytest.raises(ProviderError):
        discoverer.resolve_company("OpenAI")


def test_blank_query_returns_none_without_request() -> None:
    discoverer = GitHubCompanyDiscoverer(_settings())
    assert discoverer.resolve_company("   ") is None
