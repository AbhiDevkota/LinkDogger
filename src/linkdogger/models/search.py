"""Search result envelope shared by all interfaces."""

from datetime import datetime

from pydantic import BaseModel

from linkdogger.models.person import PersonProfile

SCHEMA_VERSION = "1.0"


class SearchResult(BaseModel):
    """Top-level result of a company search."""

    schema_version: str = SCHEMA_VERSION
    query: str
    generated_at: datetime
    count: int
    results: list[PersonProfile]
