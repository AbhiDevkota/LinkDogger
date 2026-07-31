"""LinkedIn enricher behavior.

The real ``linkedin-scraper`` package is an optional dependency (it
requires Playwright + a Chromium download), so these tests inject a fake
module via ``sys.modules`` to exercise LinkDogger's own logic.
"""

import sys
import types

import pytest

from linkdogger.enrichment.linkedin import LinkedInEnricher
from linkdogger.errors import (
    EnrichmentIncompleteError,
    RateLimitError,
    SourceUnavailableError,
)
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

PERSON_URL = "https://www.linkedin.com/in/alice-example"


class FakeAuthenticationError(Exception):
    pass


class FakeRateLimitError(Exception):
    pass


class FakeProfileNotFoundError(Exception):
    pass


class FakePerson:
    def __init__(self, **kwargs) -> None:
        self.name = kwargs.get("name", "Alice Example")
        self.headline = kwargs.get("headline", "Engineer at Acme")
        self.location = kwargs.get("location", "Berlin, Germany")
        self.about = kwargs.get("about", "Loves Go.")
        self.linkedin_url = PERSON_URL


class FakeState:
    """Shared state for the fake scraper; set by each test."""

    error: Exception | None = None
    person: FakePerson | None = None


class FakeBrowserManager:
    launched: list["FakeBrowserManager"] = []

    def __init__(self, headless: bool = True, **launch_options) -> None:
        self.headless = headless
        self.launch_options = launch_options
        self.page = None
        FakeBrowserManager.launched.append(self)

    async def __aenter__(self) -> "FakeBrowserManager":
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def load_session(self, path: str) -> None:
        self.loaded = path

    async def save_session(self, path: str) -> None:
        self.saved = path


class FakePersonScraper:
    def __init__(self, page, callback=None) -> None:
        self.page = page
        self.callback = callback
        self.urls: list[str] = []

    async def scrape(self, url: str):
        self.urls.append(url)
        if FakeState.error is not None:
            raise FakeState.error
        return FakeState.person or FakePerson()


def _install_fake_linkedin_scraper(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("linkedin_scraper")
    module.AuthenticationError = FakeAuthenticationError
    module.RateLimitError = FakeRateLimitError
    module.ProfileNotFoundError = FakeProfileNotFoundError
    module.PersonScraper = FakePersonScraper
    module.BrowserManager = FakeBrowserManager
    module.wait_for_manual_login = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "linkedin_scraper", module)
    FakeState.error = None
    FakeState.person = None
    FakeBrowserManager.launched = []


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


def _session_file(tmp_path) -> str:
    session = tmp_path / "session.json"
    session.write_text("{}")
    return str(session)


def test_unavailable_without_session_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    enricher = LinkedInEnricher()
    with pytest.raises(SourceUnavailableError, match="session file"):
        enricher.enrich_all([_person_with_linkedin()])


def test_unavailable_when_library_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "linkedin_scraper", None)
    enricher = LinkedInEnricher()
    with pytest.raises(SourceUnavailableError, match="not installed"):
        enricher.enrich_all([_person_with_linkedin()])


def test_people_without_linkedin_url_are_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    enricher = LinkedInEnricher()
    person = PersonProfile(name="Bob", company="Acme", sources=["mock-sample-data"])
    assert enricher.enrich_all([person]) == [person]


def test_enriches_person_with_scraped_data(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    enricher = LinkedInEnricher()
    enricher._session_file = _session_file(tmp_path)  # noqa: SLF001
    person = _person_with_linkedin()
    result = enricher.enrich_all([person])
    assert result[0].name == "Alice"  # name already known, not overwritten
    assert result[0].position == "Engineer at Acme"
    assert result[0].location == "Berlin, Germany"
    assert result[0].bio == "Loves Go."
    assert "linkedin-scraper" in result[0].sources


def test_existing_data_is_not_overwritten(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    enricher = LinkedInEnricher()
    enricher._session_file = _session_file(tmp_path)  # noqa: SLF001
    person = _person_with_linkedin()
    person.position = "Known Position"
    person.bio = "Known bio"
    result = enricher.enrich_all([person])
    assert result[0].position == "Known Position"
    assert result[0].bio == "Known bio"


def test_session_file_is_loaded_from_settings(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from linkdogger.config.settings import Settings

    _install_fake_linkedin_scraper(monkeypatch)
    settings = Settings(_env_file=None, linkedin_session_file=_session_file(tmp_path))
    enricher = LinkedInEnricher(settings)
    result = enricher.enrich_all([_person_with_linkedin()])
    assert result[0].position == "Engineer at Acme"


def test_browser_is_launched_with_anti_detection_options(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    enricher = LinkedInEnricher()
    enricher._session_file = _session_file(tmp_path)  # noqa: SLF001
    result = enricher.enrich_all([_person_with_linkedin()])
    assert result[0].position == "Engineer at Acme"
    last_manager = FakeBrowserManager.launched[-1]  # type: ignore[attr-defined]
    assert last_manager.launch_options["channel"] == "chrome"
    launched_args = last_manager.launch_options["args"]
    assert "--disable-blink-features=AutomationControlled" in launched_args


def test_auth_error_raises_unavailable(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    FakeState.error = FakeAuthenticationError("expired")
    enricher = LinkedInEnricher()
    enricher._session_file = _session_file(tmp_path)  # noqa: SLF001
    with pytest.raises(SourceUnavailableError, match="session expired"):
        enricher.enrich_all([_person_with_linkedin()])


def test_rate_limit_propagates(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    FakeState.error = FakeRateLimitError("slow down")
    enricher = LinkedInEnricher()
    enricher._session_file = _session_file(tmp_path)  # noqa: SLF001
    with pytest.raises(RateLimitError):
        enricher.enrich_all([_person_with_linkedin()])


def test_profile_not_found_is_partial(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    FakeState.error = FakeProfileNotFoundError("gone")
    enricher = LinkedInEnricher()
    enricher._session_file = _session_file(tmp_path)  # noqa: SLF001
    with pytest.raises(EnrichmentIncompleteError, match="skipped"):
        enricher.enrich_all([_person_with_linkedin()])


def test_enrichment_pipeline_marks_linkedin_status(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a service with the enricher reports linkedin status."""
    from linkdogger.config.settings import Settings
    from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
    from linkdogger.enrichment.social import XEnricher
    from linkdogger.services.people_service import PeopleService

    _install_fake_linkedin_scraper(monkeypatch)
    settings = Settings(_env_file=None, linkedin_session_file=_session_file(tmp_path))
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
    assert all("linkedin-scraper" in p.sources for p in enriched)
