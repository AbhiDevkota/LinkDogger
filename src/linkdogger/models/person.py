"""Person profile data model."""

from pydantic import BaseModel, Field

from linkdogger.models.networking import NetworkingScore
from linkdogger.models.social import SocialProfile


class PersonProfile(BaseModel):
    """A publicly discoverable person associated with a company.

    Fields are nullable when information is not available. Never
    fabricate placeholder values (e.g. follower counts of 0 when the
    true value is unknown).
    """

    name: str
    company: str | None = None
    position: str | None = None
    location: str | None = None
    bio: str | None = None
    profiles: dict[str, SocialProfile] = Field(default_factory=dict)
    networking: NetworkingScore | None = None
    sources: list[str] = Field(default_factory=list)
