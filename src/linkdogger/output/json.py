"""Structured JSON output."""

from linkdogger.models.search import SearchResult


def render_json(result: SearchResult) -> str:
    """Serialize a ``SearchResult`` to pretty-printed JSON."""
    return result.model_dump_json(indent=2)
