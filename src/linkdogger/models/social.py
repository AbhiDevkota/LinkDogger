"""Social profile data model."""

from pydantic import BaseModel


class SocialProfile(BaseModel):
    """A social/professional profile link for a person."""

    platform: str
    url: str | None = None
    username: str | None = None
    followers: int | None = None
    following: int | None = None
    verified: bool | None = None
    source: str
    confidence: float | None = None
    identity_confidence: float | None = None
