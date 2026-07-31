"""LinkedIn discovery behavior."""

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


class FakeCompany:
    def __init__(self, name: str = "OpenAI", about: str | None = None) -> None:
        self.name = name
        if about is not None:
            self.about = about


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


class FakeCompanyScraper:
    error: Exception | None = None
    company: FakeCompany | None = None

    def __init__(self, page, callback=None) -> None:
        self.page = page

    async def scrape(self, url: str):
        if FakeCompanyScraper.error is not None:
            raise FakeCompanyScraper.error
        return FakeCompanyScraper.company or FakeCompany()


def _install_fake_linkedin_scraper(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("linkedin_scraper")
    module.CompanyScraper = FakeCompanyScraper
    module.BrowserManager = FakeBrowserManager
    monkeypatch.setitem(sys.modules, "linkedin_scraper", module)
    FakeCompanyScraper.error = None
    FakeCompanyScraper.company = None
    FakeBrowserManager.launched = []


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _session_file(tmp_path) -> str:
    session = tmp_path / "session.json"
    session.write_text("{}")
    return str(session)


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


def test_people_discovery_reports_unavailable() -> None:
    discoverer = LinkedInPeopleDiscoverer(_settings())
    company = Company(
        name="Acme", aliases=["acme"], source="linkedin-slug", resolved_from="acme"
    )
    with pytest.raises(SourceUnavailableError, match="employee directories"):
        discoverer.discover_people(company)


def test_company_verification_with_session_and_about(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    FakeCompanyScraper.company = FakeCompany(name="OpenAI", about="AGI lab")
    discoverer = LinkedInCompanyDiscoverer(
        _settings(linkedin_session_file=_session_file(tmp_path))
    )
    company = discoverer.resolve_company("OpenAI")
    assert company is not None
    assert company.name == "OpenAI"
    assert company.description == "AGI lab"
    assert company.source == "linkedin-scraper"
    last_manager = FakeBrowserManager.launched[-1]  # type: ignore[attr-defined]
    assert last_manager.launch_options["channel"] == "chrome"


def test_company_verification_tolerates_missing_about(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    discoverer = LinkedInCompanyDiscoverer(
        _settings(linkedin_session_file=_session_file(tmp_path))
    )
    company = discoverer.resolve_company("OpenAI")
    assert company is not None
    assert company.source == "linkedin-scraper"
    assert company.description is None


def test_company_verification_falls_back_to_slug_on_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_linkedin_scraper(monkeypatch)
    FakeCompanyScraper.error = RuntimeError("Locator.inner_text: Timeout")
    discoverer = LinkedInCompanyDiscoverer(
        _settings(linkedin_session_file=_session_file(tmp_path))
    )
    company = discoverer.resolve_company("OpenAI")
    assert company is not None
    assert company.source == "linkedin-slug"
