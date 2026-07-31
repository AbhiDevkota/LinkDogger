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


def _commit_search_payload(email: str) -> dict:
    return {
        "items": [
            {
                "commit": {
                    "author": {"name": "Alice Example", "email": email},
                }
            }
        ]
    }


def test_enriches_person_with_public_user_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/alice-dev":
            return httpx.Response(200, json=_user_payload())
        assert request.url.path == "/search/commits"
        return httpx.Response(200, json=_commit_search_payload("alice@example.com"))

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    people = enricher.enrich_all([_person()])

    person = people[0]
    assert person.name == "Alice Example"
    assert person.bio == "ML engineer"
    assert person.location == "Berlin"
    assert person.email == "alice@example.com"
    assert person.profiles["github"].followers == 120
    assert person.profiles["github"].following == 45
    assert person.profiles["website"].url == "https://alice.example.com"
    assert person.profiles["x"].username == "alice_dev"
    assert person.profiles["x"].url == "https://x.com/alice_dev"
    assert "github-api" in person.sources


def test_public_email_is_used_when_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {**_user_payload(), "email": "alice@example.com"}
        return httpx.Response(200, json=payload)

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    person = enricher.enrich_all([_person()])[0]
    assert person.email == "alice@example.com"


def test_missing_public_email_falls_back_to_commit_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/alice-dev":
            return httpx.Response(200, json=_user_payload())
        assert request.url.path == "/search/commits"
        assert "author:alice-dev" in request.url.query.decode()
        assert request.headers["Accept"] == "application/vnd.github.cloak-preview+json"
        return httpx.Response(200, json=_commit_search_payload("alice@example.com"))

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    person = enricher.enrich_all([_person()])[0]
    assert person.email == "alice@example.com"


def test_noreply_email_is_dropped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/alice-dev":
            return httpx.Response(
                200,
                json={
                    **_user_payload(),
                    "email": "1234+alice@users.noreply.github.com",
                },
            )  # noqa: E501
        return httpx.Response(
            200, json=_commit_search_payload("1234+alice@users.noreply.github.com")
        )  # noqa: E501

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    person = enricher.enrich_all([_person()])[0]
    assert person.email is None


def test_failed_commit_lookup_is_silently_ignored() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/alice-dev":
            return httpx.Response(200, json=_user_payload())
        return httpx.Response(403, json={"message": "rate limited"})

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    person = enricher.enrich_all([_person()])[0]
    assert person.email is None
    assert person.name == "Alice Example"


def test_linkedin_url_in_bio_is_detected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            **_user_payload(),
            "bio": "See https://www.linkedin.com/in/alice-example",
        }
        return httpx.Response(200, json=payload)

    enricher = GitHubEnricher(_settings(), transport=httpx.MockTransport(handler))
    person = enricher.enrich_all([_person()])[0]
    assert person.profiles["linkedin"].username == "alice-example"
    assert (
        person.profiles["linkedin"].url == "https://www.linkedin.com/in/alice-example"
    )


def test_bio_without_linkedin_adds_nothing() -> None:
    enricher = GitHubEnricher(
        _settings(),
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=_user_payload())
        ),  # noqa: E501
    )
    person = enricher.enrich_all([_person()])[0]
    assert "linkedin" not in person.profiles


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
