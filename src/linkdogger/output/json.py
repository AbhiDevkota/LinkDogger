"""Structured JSON output."""

import json

from linkdogger.models.search import SearchResult


def render_json(result: SearchResult) -> str:
    """Serialize a ``SearchResult`` to pretty-printed JSON.

    Uses ``json.dumps`` rather than pydantic's ``model_dump_json``:
    pydantic emits raw control characters (e.g. ``\\r`` inside a person's
    bio) which make the document invalid JSON, while ``json.dumps``
    escapes them as valid ``\\r`` sequences.
    """
    return json.dumps(result.model_dump(mode="json"), indent=2)
