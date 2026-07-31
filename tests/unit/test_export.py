"""Result export (JSON / CSV / Markdown)."""

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from linkdogger.models.networking import NetworkingScore
from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SearchResult
from linkdogger.models.social import SocialProfile
from linkdogger.output.export import export_result, render_csv, render_markdown
from linkdogger.output.json import render_json


def _result() -> SearchResult:
    return SearchResult(
        query="Acme",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        count=1,
        results=[
            PersonProfile(
                name="Alice Example",
                company="Acme Corporation",
                position="Engineer",
                location="Berlin",
                profiles={
                    "github": SocialProfile(
                        platform="github",
                        url="https://github.com/alice-dev",
                        username="alice-dev",
                        followers=120,
                        source="test",
                    )
                },
                networking=NetworkingScore(
                    follow_back_likelihood=60,
                    influence_score=30,
                    networking_score=55,
                    confidence=0.8,
                ),
                sources=["test"],
            )
        ],
    )


def test_export_json_matches_render_json(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    export_result(_result(), path)
    exported = json.loads(path.read_text(encoding="utf-8"))
    expected = json.loads(render_json(_result()))
    assert exported == expected


def test_export_csv_contains_header_and_rows(tmp_path: Path) -> None:
    path = tmp_path / "results.csv"
    export_result(_result(), path)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    assert len(rows) == 1
    assert rows[0]["name"] == "Alice Example"
    assert rows[0]["github"] == "https://github.com/alice-dev"
    assert rows[0]["networking_score"] == "55"


def test_export_markdown_contains_table(tmp_path: Path) -> None:
    path = tmp_path / "results.md"
    export_result(_result(), path)
    text = path.read_text(encoding="utf-8")
    assert "# LinkDogger search: Acme" in text
    assert "| Alice Example" in text
    assert "| 60% |" in text


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    path = tmp_path / "results.xlsx"
    with pytest.raises(ValueError, match="unsupported export format"):
        export_result(_result(), path)


def test_render_csv_flattens_missing_fields_to_dash() -> None:
    result = SearchResult(
        query="Acme",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        count=1,
        results=[PersonProfile(name="No Data", company="Acme")],
    )
    rows = list(csv.DictReader(io.StringIO(render_csv(result))))
    assert rows[0]["followers"] == "-"
    assert rows[0]["networking_score"] == "-"
    assert rows[0]["email"] == "-"


def test_render_csv_includes_email_column() -> None:
    result = SearchResult(
        query="Acme",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        count=1,
        results=[
            PersonProfile(name="Alice", company="Acme", email="alice@example.com")
        ],
    )
    rows = list(csv.DictReader(io.StringIO(render_csv(result))))
    assert rows[0]["email"] == "alice@example.com"


def test_render_markdown_includes_email_and_accounts() -> None:
    result = SearchResult(
        query="Acme",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        count=1,
        results=[
            PersonProfile(
                name="Alice",
                company="Acme",
                email="alice@example.com",
                profiles={
                    "github": SocialProfile(
                        platform="github",
                        url="https://github.com/alice-dev",
                        username="alice-dev",
                        source="test",
                    )
                },
            )
        ],
    )
    text = render_markdown(result)
    assert "| Email |" in text
    assert "alice@example.com" in text
    assert "[github](https://github.com/alice-dev)" in text


def test_render_markdown_escapes_pipes() -> None:
    result = SearchResult(
        query="Acme",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        count=1,
        results=[PersonProfile(name="A|B", company="Acme")],
    )
    assert "A\\|B" in render_markdown(result)
