"""LinkedIn discovery behavior."""

import json
import sys
import types

import pytest

from linkdogger.config.settings import Settings
from linkdogger.discovery.linkedin import (
    LinkedInCompanyDiscoverer,
    LinkedInPeopleDiscoverer,
)
from linkdogger.errors import SourceUnavailableError
from linkdogger.models.company import Company


class FakeClient:
    companies: list[dict] = []
    company: dict | None = None
    people: list[dict] = []
    errors: list[Exception] = []
    company_search_calls: list[dict] = []
    company_lookups: list[str] = []
    people_search_calls: list[dict] = []

    def search_companies(self, keywords=None, **kwargs):
        FakeClient.company_search_calls.append(
            {"keywords": keywords or [], "kwargs": kwargs}
        )
        if FakeClient.errors:
            raise FakeClient.errors.pop(0)
        return FakeClient.companies

    def get_company(self, public_id):
        FakeClient.company_lookups.append(public_id)
        return FakeClient.company

    def search_people(self, keywords=None, current_company=None, limit=-1, **kwargs):
        FakeClient.people_search_calls.append(
            {
                "keywords": keywords,
                "current_company": current_company,
                "limit": limit,
                "kwargs": kwargs,
            }
        )
        if FakeClient.errors:
            raise FakeClient.errors.pop(0)
        return FakeClient.people


class FakeLinkedin(FakeClient):
    instances: list[dict] = []

    def __init__(
        self,
        username: str,
        password: str,
        *,
        authenticate: bool = True,
        refresh_cookies: bool = False,
        cookies_dir: str = "",
        cookies=None,
    ) -> None:
        FakeLinkedin.instances.append(
            {
                "username": username,
                "password": password,
                "cookies_dir": cookies_dir,
                "cookies": cookies,
            }
        )


def _install_fake_linkedin_api(monkeypatch: pytest.MonkeyPatch) -> None:
    package = types.ModuleType("open_linkedin_api")
    client_module = types.ModuleType("open_linkedin_api.client")
    client_module.ChallengeException = Exception
    client_module.UnauthorizedException = Exception
    repository_module = types.ModuleType("open_linkedin_api.cookie_repository")
    repository_module.LinkedinSessionExpired = Exception
    package.client = client_module
    package.cookie_repository = repository_module
    package.Linkedin = FakeLinkedin
    monkeypatch.setitem(sys.modules, "open_linkedin_api", package)
    monkeypatch.setitem(sys.modules, "open_linkedin_api.client", client_module)
    monkeypatch.setitem(
        sys.modules, "open_linkedin_api.cookie_repository", repository_module
    )
    FakeClient.companies = []
    FakeClient.company = None
    FakeClient.people = []
    FakeClient.errors = []
    FakeClient.company_search_calls = []
    FakeClient.company_lookups = []
    FakeClient.people_search_calls = []
    FakeLinkedin.instances = []


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _creds(**overrides) -> dict:
    creds = {"linkedin_email": "me@acme.com", "linkedin_password": "pw"}
    creds.update(overrides)
    return creds


def _company(**overrides) -> Company:
    data = {
        "name": "Acme",
        "aliases": ["acme"],
        "source": "linkedin-slug",
        "resolved_from": "acme",
    }
    data.update(overrides)
    return Company(**data)


def test_company_resolved_from_query_slug() -> None:
    discoverer = LinkedInCompanyDiscoverer(_settings())
    company = discoverer.resolve_company("Microsoft")
    assert company is not None
    assert company.name == "Microsoft"
    assert company.aliases == ["microsoft"]
    assert company.source == "linkedin-slug"


def test_company_slug_normalizes_query() -> None:
    discoverer = LinkedInCompanyDiscoverer(_settings())
    company = discoverer.resolve_company("Open AI Inc.")
    assert company is not None
    assert company.aliases == ["open-ai-inc"]


def test_blank_query_returns_none() -> None:
    discoverer = LinkedInCompanyDiscoverer(_settings())
    assert discoverer.resolve_company("   ") is None


def test_company_resolved_via_search_companies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.companies = [
        {"urn_id": "1234", "name": "OpenAI", "headline": "AGI lab", "subline": None}
    ]
    discoverer = LinkedInCompanyDiscoverer(_settings(**_creds()))
    company = discoverer.resolve_company("OpenAI")
    assert company is not None
    assert company.name == "OpenAI"
    assert company.description == "AGI lab"
    assert company.source == "linkedin-api"
    assert company.aliases == ["1234", "openai"]
    assert FakeClient.company_search_calls == [
        {"keywords": ["OpenAI"], "kwargs": {"limit": 5}}
    ]


def test_company_falls_back_to_slug_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.errors = [RuntimeError("boom")]
    discoverer = LinkedInCompanyDiscoverer(_settings(**_creds()))
    company = discoverer.resolve_company("OpenAI")
    assert company is not None
    assert company.source == "linkedin-slug"
    assert company.aliases == ["openai"]


def test_company_falls_back_to_get_company_when_search_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.company = {"name": "OpenAI", "description": "AGI lab"}
    discoverer = LinkedInCompanyDiscoverer(_settings(**_creds()))
    company = discoverer.resolve_company("OpenAI")
    assert company is not None
    assert company.source == "linkedin-api"
    assert company.description == "AGI lab"
    assert company.aliases == ["openai"]
    assert FakeClient.company_lookups == ["openai"]


def test_company_without_credentials_skips_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    discoverer = LinkedInCompanyDiscoverer(_settings())
    company = discoverer.resolve_company("OpenAI")
    assert company is not None
    assert company.source == "linkedin-slug"
    assert FakeClient.company_search_calls == []


def test_people_search_failure_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.errors = [RuntimeError("request failed")]
    discoverer = LinkedInPeopleDiscoverer(_settings(**_creds()))
    with pytest.raises(SourceUnavailableError, match="people search failed"):
        discoverer.discover_people(_company())


def test_people_discovery_uses_company_urn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.people = [
        {
            "urn_id": "99",
            "name": "Alice A",
            "jobtitle": "Engineer",
            "location": "Berlin",
        }
    ]
    discoverer = LinkedInPeopleDiscoverer(_settings(**_creds()))
    people = discoverer.discover_people(_company(aliases=["1234", "acme"]))
    assert len(people) == 1
    person = people[0]
    assert person.name == "Alice A"
    assert person.position == "Engineer"
    assert person.location == "Berlin"
    assert person.sources == ["linkedin-api"]
    linkedin = person.profiles["linkedin"]
    assert linkedin.username == "99"
    assert linkedin.url is None
    assert FakeClient.people_search_calls == [
        {
            "keywords": None,
            "current_company": ["1234"],
            "limit": 100,
            "kwargs": {"include_private_profiles": True},
        }
    ]


def test_people_discovery_falls_back_to_keywords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.people = []
    discoverer = LinkedInPeopleDiscoverer(_settings(**_creds()))
    discoverer.discover_people(_company())
    assert FakeClient.people_search_calls == [
        {
            "keywords": "Acme",
            "current_company": None,
            "limit": 100,
            "kwargs": {"include_private_profiles": True},
        }
    ]


def test_people_discovery_requires_credentials() -> None:
    discoverer = LinkedInPeopleDiscoverer(_settings())
    with pytest.raises(SourceUnavailableError, match="credentials"):
        discoverer.discover_people(_company())


def test_people_discovery_skips_nameless_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.people = [
        {"urn_id": "1", "name": "Alice A", "jobtitle": "Engineer"},
        {"urn_id": "2", "name": None, "jobtitle": "Engineer"},
    ]
    discoverer = LinkedInPeopleDiscoverer(_settings(**_creds()))
    people = discoverer.discover_people(_company(aliases=["1234", "acme"]))
    assert len(people) == 1
    assert people[0].name == "Alice A"


def test_people_discovery_respects_max_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.people = []
    discoverer = LinkedInPeopleDiscoverer(_settings(**_creds(max_results=5)))
    discoverer.discover_people(_company())
    assert FakeClient.people_search_calls[0]["limit"] == 5


def test_people_discovery_with_cookie_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.people = [{"urn_id": "1", "name": "Alice A", "jobtitle": "Engineer"}]
    cookie_file = tmp_path / "linkedin-cookies.json"
    cookie_file.write_text(
        json.dumps({"li_at": "abc123", "JSESSIONID": "ajax:xyz"}),
        encoding="utf-8",
    )
    discoverer = LinkedInPeopleDiscoverer(
        _settings(linkedin_cookie_file=str(cookie_file))
    )
    people = discoverer.discover_people(_company())
    assert len(people) == 1
    assert FakeLinkedin.instances[0]["cookies"] is not None
