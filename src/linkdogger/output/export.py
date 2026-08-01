"""Result export to JSON, CSV and Markdown.

The JSON export is the canonical, versioned machine-readable format;
CSV and Markdown are flattened views for humans and spreadsheets.
``export_emails`` writes just the discovered email addresses, which is
the handiest artifact for outreach lists.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SearchResult
from linkdogger.output.json import render_json

JSON_SUFFIXES = (".json",)
CSV_SUFFIXES = (".csv",)
MARKDOWN_SUFFIXES = (".md", ".markdown")

EMAIL_SCHEMA_VERSION = "1.0"

_CSV_COLUMNS = [
    "name",
    "company",
    "position",
    "location",
    "email",
    "linkedin",
    "github",
    "x",
    "website",
    "followers",
    "follow_back_likelihood",
    "influence_score",
    "networking_score",
    "confidence",
    "sources",
]


def export_result(result: SearchResult, path: Path) -> str:
    """Write ``result`` to ``path``; format chosen by file extension.

    Returns a short description of what was exported.
    """
    suffix = path.suffix.lower()
    if suffix in JSON_SUFFIXES:
        path.write_text(render_json(result), encoding="utf-8")
        return f"Exported {result.count} results to {path} (JSON)"
    if suffix in CSV_SUFFIXES:
        path.write_text(render_csv(result), encoding="utf-8")
        return f"Exported {result.count} results to {path} (CSV)"
    if suffix in MARKDOWN_SUFFIXES:
        path.write_text(render_markdown(result), encoding="utf-8")
        return f"Exported {result.count} results to {path} (Markdown)"
    raise ValueError(
        f"unsupported export format '{suffix}' (expected .json, .csv or .md)"
    )


def export_emails(result: SearchResult, path: Path) -> str:
    """Write every discovered email address to ``path`` as JSON.

    Only people with an email address are included; the document lists
    them twice — a flat ``emails`` array for pasting into tools, and
    ``people`` with name/position context. Returns a short description
    of what was exported.
    """
    people = [
        {
            "name": person.name,
            "company": person.company,
            "position": person.position,
            "email": person.email,
        }
        for person in result.results
        if person.email
    ]
    payload = {
        "schema_version": EMAIL_SCHEMA_VERSION,
        "query": result.query,
        "company": result.company.name if result.company else None,
        "generated_at": result.generated_at.isoformat(),
        "count": len(people),
        "emails": [entry["email"] for entry in people],
        "people": people,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return f"Exported {len(people)} email(s) to {path} (JSON)"


def render_csv(result: SearchResult) -> str:
    """Flatten search results into CSV text."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    for person in result.results:
        writer.writerow(_flatten(person))
    return buffer.getvalue()


def render_markdown(result: SearchResult) -> str:
    """Render search results as a Markdown table."""
    lines = [
        f"# LinkDogger search: {result.query}",
        "",
        f"Generated at: {result.generated_at.isoformat()}",
        f"Found {result.count} publicly discoverable people",
        "",
        "| Name | Position | Location | Email | Accounts | Followers "
        "| Networking | Follow-back |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for person in result.results:
        lines.append(
            "| {name} | {position} | {location} | {email} | {accounts} | "
            "{followers} | {network} | {followback} |".format(
                name=_escape_md(person.name),
                position=_escape_md(person.position or "-"),
                location=_escape_md(person.location or "-"),
                email=person.email or "-",
                accounts=_markdown_accounts(person),
                followers=_format_followers(_max_followers(person)),
                network=_format_int(
                    person.networking.networking_score if person.networking else None
                ),
                followback=_format_percent(
                    person.networking.follow_back_likelihood
                    if person.networking
                    else None
                ),
            )
        )
    return "\n".join(lines) + "\n"


def _markdown_accounts(person: PersonProfile) -> str:
    links = []
    for platform, profile in person.profiles.items():
        if profile.url:
            label = "X" if platform == "x" else platform
            links.append(f"[{_escape_md(label)}]({profile.url})")
    return ", ".join(links) if links else "-"


def _flatten(person: PersonProfile) -> dict[str, str | None]:
    return {
        "name": person.name,
        "company": person.company,
        "position": person.position,
        "location": person.location,
        "email": person.email or "-",
        "linkedin": _url_for(person, "linkedin"),
        "github": _url_for(person, "github"),
        "x": _url_for(person, "x"),
        "website": _url_for(person, "website"),
        "followers": _format_followers(_max_followers(person)),
        "follow_back_likelihood": _format_percent(
            person.networking.follow_back_likelihood if person.networking else None
        ),
        "influence_score": _format_int(
            person.networking.influence_score if person.networking else None
        ),
        "networking_score": _format_int(
            person.networking.networking_score if person.networking else None
        ),
        "confidence": (
            str(person.networking.confidence) if person.networking else None
        ),
        "sources": ", ".join(person.sources),
    }


def _url_for(person: PersonProfile, platform: str) -> str | None:
    profile = person.profiles.get(platform)
    return profile.url if profile else None


def _max_followers(person: PersonProfile) -> int | None:
    counts = [
        profile.followers
        for profile in person.profiles.values()
        if profile.followers is not None
    ]
    return max(counts) if counts else None


def _format_followers(count: int | None) -> str:
    if count is None:
        return "-"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def _format_int(value: int | None) -> str:
    return "-" if value is None else str(value)


def _format_percent(value: int | None) -> str:
    return "-" if value is None else f"{value}%"


def _escape_md(value: str) -> str:
    return value.replace("|", "\\|")
