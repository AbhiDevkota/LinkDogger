"""Search result envelope shared by all interfaces."""

from datetime import datetime

from pydantic import BaseModel, Field

from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile

SCHEMA_VERSION = "1.0"


class SearchResult(BaseModel):
    """Top-level result of a company search."""

    schema_version: str = SCHEMA_VERSION
    query: str
    generated_at: datetime
    count: int
    company: Company | None = None
    results: list[PersonProfile] = Field(default_factory=list)
    source_status: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
