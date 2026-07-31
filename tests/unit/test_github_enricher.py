"""GitHub profile enrichment adapter."""

import httpx
import pytest

from linkdogger.config.settings import Settings
from linkdogger.enrichment.github import GitHubEnricher
from linkdogger.errors import EnrichmentIncompleteError, RateLimitError
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile


def _settings() -> Settings:
    return Settings(_env_file=None)


def _person(login: str = "alice-dev") -> PersonProfile:
    return PersonProfile(
        name=login,
        company="OpenAI",
        profiles={
            "github": SocialProfile(
                platform="github",
                url=f"https://github.com/{login}",
                username=login,
                source="github-api",
            )
        },
        sources=["github-api"],
    )


def _user_payload(login: str = "alice-dev") -> dict:
    return {
        "login": login,
        "name": "Alice Example",
        "bio": "ML engineer",
        "location": "Berlin",
        "company": "OpenAI",
        "followers": 120,
        "following": 45,
        "blog": "https://alice.example.com",
        "twitter_username": "alice_dev",
    }


def test_enriches_person_with_public_user_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/users/alice-dev"
        return httpx.Response(200, json=_user_payload())

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    people = enricher.enrich_all([_person()])

    person = people[0]
    assert person.name == "Alice Example"
    assert person.bio == "ML engineer"
    assert person.location == "Berlin"
    assert person.profiles["github"].followers == 120
    assert person.profiles["github"].following == 45
    assert person.profiles["website"].url == "https://alice.example.com"
    assert person.profiles["x"].username == "alice_dev"
    assert person.profiles["x"].url == "https://x.com/alice_dev"
    assert "github-api" in person.sources


def test_person_without_github_profile_is_left_alone() -> None:
    enricher = GitHubEnricher(_settings())
    person = PersonProfile(name="No GitHub", company="Acme")
    people = enricher.enrich_all([person])
    assert people == [person]


def test_per_person_failure_is_isolated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/missing-user":
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(200, json=_user_payload())

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    people = [
        _person("missing-user"),
        _person("alice-dev"),
    ]
    with pytest.raises(EnrichmentIncompleteError):
        enricher.enrich_all(people)


def test_rate_limit_propagates() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(403, json={"message": "rate limited"})
    )
    enricher = GitHubEnricher(_settings(), transport=transport)
    with pytest.raises(RateLimitError):
        enricher.enrich_all([_person()])


def test_blog_without_http_scheme_is_not_added() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {**_user_payload(), "blog": "alice.example.com"}
        return httpx.Response(200, json=payload)

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    person = enricher.enrich_all([_person()])[0]
    assert "website" not in person.profiles
