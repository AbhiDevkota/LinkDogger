"""JSON serialization of search results."""

import json
from datetime import UTC, datetime

from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SearchResult
from linkdogger.output.json import render_json


def _sample_result() -> SearchResult:
    return SearchResult(
        query="Acme",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        count=1,
        results=[
            PersonProfile(name="Alex Sample", company="Acme", position="Engineer")
        ],
    )


def test_render_json_round_trips() -> None:
    payload = json.loads(render_json(_sample_result()))
    assert payload["schema_version"] == "1.0"
    assert payload["query"] == "Acme"
    assert payload["generated_at"] == "2026-01-01T00:00:00Z"
    assert payload["count"] == 1
    assert payload["results"][0]["name"] == "Alex Sample"


def test_nullable_fields_serialize_as_null() -> None:
    payload = json.loads(render_json(_sample_result()))
    assert payload["results"][0]["location"] is None
    assert payload["results"][0]["profiles"] == {}
    assert payload["results"][0]["networking"] is None
