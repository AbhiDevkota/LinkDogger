"""Company data model."""

from pydantic import BaseModel, Field


class Company(BaseModel):
    """A resolved company entity discovered from a user query."""

    name: str
    aliases: list[str] = Field(default_factory=list)
    domain: str | None = None
    description: str | None = None
    source: str
    resolved_from: str
