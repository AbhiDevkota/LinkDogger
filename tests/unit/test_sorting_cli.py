"""Sorting/filtering through the CLI and service."""

import json

from typer.testing import CliRunner

from linkdogger.cli import app
from linkdogger.config.settings import Settings
from linkdogger.discovery.mock import MockCompanyDiscoverer, MockPeopleDiscoverer
from linkdogger.services.people_service import PeopleService
from linkdogger.services.processing import ResultFilters, SortKey

runner = CliRunner()


def test_search_sort_by_name() -> None:
    result = runner.invoke(app, ["search", "Acme", "--sort", "name-asc"])
    assert result.exit_code == 0
    payload = json.loads(runner.invoke(app, ["search", "Acme", "--json"]).output)
    names = [p["name"] for p in payload["results"]]
    assert names == sorted(names)


def test_search_sort_followers_desc_json() -> None:
    result = runner.invoke(
        app, ["search", "Acme", "--json", "--sort", "followers-desc"]
    )
    payload = json.loads(result.output)

    def max_followers(person: dict) -> int:
        counts = [
            profile["followers"]
            for profile in person["profiles"].values()
            if profile["followers"] is not None
        ]
        return max(counts, default=0)

    followers = [max_followers(p) for p in payload["results"]]
    assert followers == sorted(followers, reverse=True)


def test_search_role_filter() -> None:
    result = runner.invoke(app, ["search", "Acme", "--json", "--role", "engineer"])
    payload = json.loads(result.output)
    assert payload["count"] == 1
    assert payload["results"][0]["position"] == "Software Engineer"


def test_search_limit() -> None:
    result = runner.invoke(app, ["search", "Acme", "--json", "--limit", "2"])
    payload = json.loads(result.output)
    assert payload["count"] == 2


def test_search_invalid_sort_errors() -> None:
    result = runner.invoke(app, ["search", "Acme", "--sort", "bogus"])
    assert result.exit_code != 0
    assert "invalid sort" in result.output


def test_service_applies_sort_and_filters() -> None:
    service = PeopleService(
        Settings(_env_file=None),
        MockCompanyDiscoverer(),
        MockPeopleDiscoverer(),
    )
    result = service.search_company(
        "Acme",
        sort=(SortKey.NAME, "asc"),
        filters=ResultFilters(location="San Francisco"),
    )
    assert result.count == 1
    assert result.results[0].name == "Alex Sample"
