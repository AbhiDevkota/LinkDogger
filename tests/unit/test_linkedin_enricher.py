"""LinkedIn enricher behavior.

The real ``open-linkedin-api`` package makes live network calls, so
these tests inject a fake module via ``sys.modules`` to exercise
LinkDogger's own logic.
"""

import json
import sys
import types

import pytest

from linkdogger.enrichment.linkedin import LinkedInEnricher
from linkdogger.errors import (
    EnrichmentIncompleteError,
    SourceUnavailableError,
)
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

PERSON_URL = "https://www.linkedin.com/in/alice-example"


class FakeChallengeError(Exception):
    pass


class FakeUnauthorizedError(Exception):
    pass


class FakeSessionExpired(Exception):
    pass


class FakeClient:
    profiles: dict[str, dict] = {}
    contacts: dict[str, dict] = {}
    errors: list[Exception] = []
    calls: list[tuple[str, str | None, str | None]] = []
    dash_profiles: dict[str, dict] = {}
    dash_errors: list[Exception] = []
    dash_fetch_calls: list[str] = []

    def get_profile(self, public_id=None, urn_id=None):
        FakeClient.calls.append(("profile", public_id, urn_id))
        if FakeClient.errors:
            raise FakeClient.errors.pop(0)
        return FakeClient.profiles.get(public_id or urn_id, {})

    def get_profile_contact_info(self, public_id=None, urn_id=None):
        FakeClient.calls.append(("contact", public_id, urn_id))
        return FakeClient.contacts.get(public_id or urn_id, {})

    def _fetch(self, uri: str) -> "_FakeResponse":
        FakeClient.dash_fetch_calls.append(uri)
        if FakeClient.dash_errors:
            raise FakeClient.dash_errors.pop(0)
        identifier = uri.split("memberIdentity=", 1)[-1]
        return _FakeResponse(FakeClient.dash_profiles.get(identifier))


class _FakeResponse:
    status_code = 200

    def __init__(self, body: dict | None) -> None:
        self._body = body

    def json(self) -> dict:
        return self._body or {}


class FakeLinkedin(FakeClient):
    instances: list[dict] = []
    errors: list[Exception] = []

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
                "authenticate": authenticate,
                "refresh_cookies": refresh_cookies,
                "cookies_dir": cookies_dir,
                "cookies": cookies,
            }
        )
        if FakeLinkedin.errors:
            raise FakeLinkedin.errors.pop(0)
        self.client = FakeLibraryClient()


class FakeLibrarySession:
    calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs) -> None:
        FakeLibrarySession.calls.append((method, url, kwargs))


class FakeLibraryClient:
    def __init__(self) -> None:
        self.session = FakeLibrarySession()


def _install_fake_linkedin_api(monkeypatch: pytest.MonkeyPatch) -> None:
    package = types.ModuleType("open_linkedin_api")
    client_module = types.ModuleType("open_linkedin_api.client")
    client_module.ChallengeException = FakeChallengeError
    client_module.UnauthorizedException = FakeUnauthorizedError
    repository_module = types.ModuleType("open_linkedin_api.cookie_repository")
    repository_module.LinkedinSessionExpired = FakeSessionExpired
    package.client = client_module
    package.cookie_repository = repository_module
    package.Linkedin = FakeLinkedin
    monkeypatch.setitem(sys.modules, "open_linkedin_api", package)
    monkeypatch.setitem(sys.modules, "open_linkedin_api.client", client_module)
    monkeypatch.setitem(
        sys.modules, "open_linkedin_api.cookie_repository", repository_module
    )
    FakeClient.profiles = {}
    FakeClient.contacts = {}
    FakeClient.errors = []
    FakeClient.calls = []
    FakeLinkedin.instances = []
    FakeLinkedin.errors = []
    FakeLibrarySession.calls = []
    FakeClient.dash_profiles = {}
    FakeClient.dash_errors = []
    FakeClient.dash_fetch_calls = []


def _person_with_linkedin() -> PersonProfile:
    return PersonProfile(
        name="Alice",
        company="Acme",
        profiles={
            "linkedin": SocialProfile(
                platform="linkedin",
                url=PERSON_URL,
                source="github-api",
                confidence=0.9,
            )
        },
        sources=["github-api"],
    )


def _person_with_urn(username: str = "123456") -> PersonProfile:
    return PersonProfile(
        name="Bob",
        company="Acme",
        profiles={
            "linkedin": SocialProfile(
                platform="linkedin",
                url=None,
                username=username,
                source="linkedin-api",
                confidence=0.7,
            )
        },
        sources=["linkedin-api"],
    )


def _alice_profile_data() -> dict:
    return {
        "firstName": "Alice",
        "lastName": "Example",
        "headline": "Engineer at Acme",
        "locationName": "Berlin, Germany",
        "summary": "Loves Go.",
        "public_id": "alice-example",
    }


def test_unavailable_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_linkedin_api(monkeypatch)
    enricher = LinkedInEnricher()
    with pytest.raises(SourceUnavailableError, match="credentials"):
        enricher.enrich_all([_person_with_linkedin()])


def test_unavailable_when_library_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "open_linkedin_api", None)
    enricher = LinkedInEnricher()
    with pytest.raises(SourceUnavailableError, match="not installed"):
        enricher.enrich_all([_person_with_linkedin()])


def test_people_without_linkedin_profile_are_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    enricher = LinkedInEnricher()
    person = PersonProfile(name="Bob", company="Acme", sources=["mock-sample-data"])
    assert enricher.enrich_all([person]) == [person]
    assert FakeLinkedin.instances == []


def test_enriches_person_with_profile_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    enricher = LinkedInEnricher()
    enricher._email = "alice@acme.com"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    result = enricher.enrich_all([_person_with_linkedin()])
    assert result[0].name == "Alice"  # name already known, not overwritten
    assert result[0].position == "Engineer at Acme"
    assert result[0].location == "Berlin, Germany"
    assert result[0].bio == "Loves Go."
    assert "linkedin-api" in result[0].sources
    assert result[0].profiles["linkedin"].username == "alice-example"


def test_existing_data_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    person = _person_with_linkedin()
    person.position = "Known Position"
    person.bio = "Known bio"
    result = enricher.enrich_all([person])
    assert result[0].position == "Known Position"
    assert result[0].bio == "Known bio"


def test_email_from_contact_info_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    FakeClient.contacts["alice-example"] = {"email_address": "alice@acme.com"}
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    result = enricher.enrich_all([_person_with_linkedin()])
    assert result[0].email == "alice@acme.com"
    assert ("contact", "alice-example", None) in FakeClient.calls


def test_existing_email_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    person = _person_with_linkedin()
    person.email = "known@acme.com"
    enricher.enrich_all([person])
    assert FakeClient.calls == [("profile", "alice-example", None)]


def test_credentials_are_taken_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from linkdogger.config.settings import Settings

    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    settings = Settings(
        _env_file=None,
        linkedin_email="me@acme.com",
        linkedin_password="pw",
        linkedin_cookies_dir="cookies/",
    )
    enricher = LinkedInEnricher(settings)
    enricher.enrich_all([_person_with_linkedin()])
    assert FakeLinkedin.instances[0]["username"] == "me@acme.com"
    assert FakeLinkedin.instances[0]["password"] == "pw"
    assert FakeLinkedin.instances[0]["cookies_dir"] == "cookies/"


def test_expired_cookies_trigger_relogin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeLinkedin.errors = [FakeSessionExpired("expired")]
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    result = enricher.enrich_all([_person_with_linkedin()])
    assert result[0].position == "Engineer at Acme"
    assert len(FakeLinkedin.instances) == 2
    assert FakeLinkedin.instances[1]["refresh_cookies"] is True


def test_auth_challenge_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeLinkedin.errors = [FakeChallengeError("CAPTCHA_CHALLENGE")]
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    with pytest.raises(SourceUnavailableError, match="challenge"):
        enricher.enrich_all([_person_with_linkedin()])


def test_unauthorized_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeLinkedin.errors = [FakeUnauthorizedError()]
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "wrong"  # noqa: SLF001
    with pytest.raises(SourceUnavailableError, match="rejected"):
        enricher.enrich_all([_person_with_linkedin()])


def test_profile_not_found_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    with pytest.raises(EnrichmentIncompleteError, match="skipped"):
        enricher.enrich_all([_person_with_linkedin()])


def test_per_person_failure_is_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    FakeClient.profiles["123456"] = {
        "firstName": "Bob",
        "lastName": "Smith",
        "headline": "Engineer at Acme",
    }
    FakeClient.errors = [RuntimeError("boom")]
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    people = [_person_with_linkedin(), _person_with_urn("123456")]
    with pytest.raises(EnrichmentIncompleteError, match="skipped"):
        enricher.enrich_all(people)
    assert people[1].position == "Engineer at Acme"


def test_urn_based_username_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["123456"] = {
        "firstName": "Bob",
        "lastName": "Smith",
        "headline": "CTO at Acme",
    }
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    result = enricher.enrich_all([_person_with_urn()])
    assert FakeClient.calls[0] == ("profile", None, "123456")
    assert result[0].position == "CTO at Acme"
    assert "linkedin-api" in result[0].sources


def test_auth_error_mid_run_raises_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    FakeClient.errors = [
        RuntimeError("boom"),
        FakeChallengeError("CAPTCHA_CHALLENGE"),
    ]
    enricher = LinkedInEnricher()
    enricher._email = "a@b.c"  # noqa: SLF001
    enricher._password = "secret"  # noqa: SLF001
    with pytest.raises(SourceUnavailableError, match="session ended"):
        enricher.enrich_all([_person_with_linkedin(), _person_with_urn("123456")])


def _cookie_file(tmp_path) -> str:
    path = tmp_path / "linkedin-cookies.json"
    path.write_text(
        json.dumps({"li_at": "abc123", "JSESSIONID": "ajax:xyz"}),
        encoding="utf-8",
    )
    return str(path)


def test_session_cookies_are_used_from_file(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    enricher = LinkedInEnricher()
    enricher._cookie_file = _cookie_file(tmp_path)  # noqa: SLF001
    result = enricher.enrich_all([_person_with_linkedin()])
    assert result[0].position == "Engineer at Acme"
    instance = FakeLinkedin.instances[0]
    assert instance["cookies"] is not None
    assert instance["cookies"].get("li_at") == "abc123"
    assert instance["cookies"].get("JSESSIONID") == "ajax:xyz"


def test_cookie_file_takes_priority_over_credentials(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    enricher = LinkedInEnricher()
    enricher._email = "me@acme.com"  # noqa: SLF001
    enricher._password = "pw"  # noqa: SLF001
    enricher._cookie_file = _cookie_file(tmp_path)  # noqa: SLF001
    enricher.enrich_all([_person_with_linkedin()])
    assert FakeLinkedin.instances[0]["cookies"] is not None


def test_missing_cookie_file_raises_unavailable(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    enricher = LinkedInEnricher()
    enricher._cookie_file = str(tmp_path / "missing.json")  # noqa: SLF001
    with pytest.raises(SourceUnavailableError, match="cookie file not found"):
        enricher.enrich_all([_person_with_linkedin()])


def test_cookie_file_requires_both_cookies(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_api(monkeypatch)
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"li_at": "abc123"}), encoding="utf-8")
    enricher = LinkedInEnricher()
    enricher._cookie_file = str(path)  # noqa: SLF001
    with pytest.raises(SourceUnavailableError, match="missing li_at/JSESSIONID"):
        enricher.enrich_all([_person_with_linkedin()])


def test_cookie_file_from_settings(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from linkdogger.config.settings import Settings

    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alice-example"] = _alice_profile_data()
    settings = Settings(
        _env_file=None,
        linkedin_cookie_file=_cookie_file(tmp_path),
    )
    result = LinkedInEnricher(settings).enrich_all([_person_with_linkedin()])
    assert result[0].position == "Engineer at Acme"


def test_session_gets_default_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The library never sets a timeout, so one is injected per client."""
    _install_fake_linkedin_api(monkeypatch)
    from linkdogger.linkedin_api import get_linkedin_client

    client = get_linkedin_client("me@acme.com", "pw", timeout=42.0)
    session = client.client.session
    session.request("GET", "https://example.com")
    assert FakeLibrarySession.calls[-1][2].get("timeout") == 42.0
    session.request("GET", "https://example.com", timeout=7.0)
    assert FakeLibrarySession.calls[-1][2]["timeout"] == 7.0


def test_no_timeout_wrapper_without_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_linkedin_api(monkeypatch)
    from linkdogger.linkedin_api import get_linkedin_client

    client = get_linkedin_client("me@acme.com", "pw")
    client.client.session.request("GET", "https://example.com")
    assert "timeout" not in FakeLibrarySession.calls[-1][2]


def test_profile_falls_back_to_dash_when_library_endpoint_is_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The legacy profileView endpoint crashes the library; Dash covers it."""
    _install_fake_linkedin_api(monkeypatch)
    FakeClient.errors = [KeyError("message")]
    FakeClient.dash_profiles["alice-example"] = {
        "elements": [
            {
                "firstName": {"text": "Alice"},
                "lastName": {"text": "Example"},
                "headline": {"text": "Engineer at Acme"},
                "locationName": "Berlin, Germany",
                "publicIdentifier": "alice-example",
            }
        ]
    }
    enricher = LinkedInEnricher()
    enricher._email = "me@acme.com"  # noqa: SLF001
    enricher._password = "pw"  # noqa: SLF001
    result = enricher.enrich_all([_person_with_linkedin()])
    assert result[0].position == "Engineer at Acme"
    assert result[0].location == "Berlin, Germany"
    assert FakeClient.dash_fetch_calls == [
        "/identity/dash/profiles?q=memberIdentity&memberIdentity=alice-example"
    ]


def test_dash_failure_trips_circuit_breaker_for_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hard Dash failure must not repeat per person (each retry sleeps)."""
    _install_fake_linkedin_api(monkeypatch)
    from linkdogger.linkedin_api import get_linkedin_client, get_profile

    client = get_linkedin_client("me@acme.com", "pw")
    FakeClient.errors = [KeyError("message"), KeyError("message")]
    FakeClient.dash_errors = [RuntimeError("redirect loop")]
    assert get_profile(client, urn_id="123456") == {}
    assert get_profile(client, urn_id="654321") == {}
    assert len(FakeClient.dash_fetch_calls) == 1
    assert getattr(client, "_linkdogger_dash_broken", False) is True


def test_enrichment_pipeline_marks_linkedin_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: a service with the enricher reports linkedin status."""
    from linkdogger.config.settings import Settings
    from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
    from linkdogger.enrichment.social import XEnricher
    from linkdogger.services.people_service import PeopleService

    _install_fake_linkedin_api(monkeypatch)
    FakeClient.profiles["alex-sample"] = _alice_profile_data()
    FakeClient.profiles["jordan-sample"] = {
        "firstName": "Jordan",
        "lastName": "Sample",
        "headline": "Product Designer",
    }
    FakeClient.contacts["jordan-sample"] = {"email_address": "jordan@acme.com"}
    settings = Settings(
        _env_file=None,
        linkedin_email="me@acme.com",
        linkedin_password="pw",
    )
    service = PeopleService(
        settings,
        MockCompanyDiscoverer(),
        MockPeopleDiscoverer(),
        enrichers=[LinkedInEnricher(settings), XEnricher()],
    )
    result = service.search_company("Acme")
    assert result.count == 3
    assert result.source_status["linkedin"] == "ok"
    enriched = [p for p in result.results if "linkedin" in p.profiles]
    assert enriched
    assert all("linkedin-api" in p.sources for p in enriched)
    jordan = next(p for p in result.results if p.name == "Jordan Sample")
    assert jordan.email == "jordan@acme.com"
