"""Rich table rendering."""

from datetime import UTC, datetime

from rich.console import Console

from linkdogger.models.networking import NetworkingScore
from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SearchResult
from linkdogger.models.social import SocialProfile
from linkdogger.output.table import _format_followers, _format_percent, render_table


def _render(table) -> str:
    console = Console(record=True, width=120)
    console.print(table)
    return console.export_text()


def _result(results: list[PersonProfile], query: str = "Acme") -> SearchResult:
    return SearchResult(
        query=query,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        count=len(results),
        results=results,
    )


def _person(
    name: str,
    position: str | None = None,
    location: str | None = None,
    followers: int | None = None,
    networking: NetworkingScore | None = None,
    email: str | None = None,
) -> PersonProfile:
    profiles = {}
    if followers is not None:
        profiles["github"] = SocialProfile(
            platform="github",
            url=f"https://github.com/{name.lower().replace(' ', '-')}",
            username=name.lower(),
            followers=followers,
            source="test",
        )
    return PersonProfile(
        name=name,
        company="Acme Corporation",
        position=position,
        location=location,
        email=email,
        profiles=profiles,
        networking=networking,
    )


def test_title_contains_query() -> None:
    text = _render(render_table(_result([], query="OpenAI")))
    assert "OpenAI" in text


def test_full_row_values() -> None:
    text = _render(
        render_table(
            _result(
                [
                    _person(
                        "Alice Example",
                        position="Engineer",
                        location="Berlin",
                        followers=2500,
                        networking=NetworkingScore(
                            networking_score=80, follow_back_likelihood=60
                        ),
                    )
                ]
            )
        )
    )
    assert "Alice Example" in text
    assert "Engineer" in text
    assert "Berlin" in text
    assert "2.5K" in text
    assert "80" in text
    assert "60%" in text


def test_email_column_shows_email() -> None:
    text = _render(
        render_table(_result([_person("Alice Example", email="alice@example.com")]))
    )
    assert "alice@example.com" in text


def test_accounts_column_links_profiles() -> None:
    person = _person("Alice Example", followers=10)
    person.profiles["linkedin"] = SocialProfile(
        platform="linkedin",
        url="https://www.linkedin.com/in/alice-example",
        username="alice-example",
        source="test",
    )
    person.profiles["x"] = SocialProfile(
        platform="x",
        url="https://x.com/alice_dev",
        username="alice_dev",
        source="test",
    )
    text = _render(render_table(_result([person])))
    assert "github" in text
    assert "linkedin" in text
    assert "X" in text

    console = Console(record=True, width=120)
    console.print(render_table(_result([person])))
    html = console.export_html()
    assert 'href="https://x.com/alice_dev"' in html
    assert 'href="https://www.linkedin.com/in/alice-example"' in html
    assert 'href="https://github.com/alice-example"' in html


def test_missing_values_fall_back_to_dash() -> None:
    text = _render(render_table(_result([_person("No Data")])))
    assert "No Data" in text
    assert "| - |" in text or text.count("-") >= 6


def test_empty_results_still_renders_title() -> None:
    text = _render(render_table(_result([])))
    assert "Acme" in text
    assert "Name" in text


def test_format_followers() -> None:
    assert _format_followers(None) == "-"
    assert _format_followers(42) == "42"
    assert _format_followers(1500) == "1.5K"
    assert _format_followers(2_500_000) == "2.5M"


def test_format_percent() -> None:
    assert _format_percent(None) == "-"
    assert _format_percent(0) == "0%"
    assert _format_percent(100) == "100%"
