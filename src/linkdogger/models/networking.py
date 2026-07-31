"""Networking signal data model."""

from pydantic import BaseModel


class NetworkingScore(BaseModel):
    """Networking-related signals for a person.

    Scores are heuristics and predictions, not factual statements.
    Every field is nullable: when information is unavailable it is
    ``null``, never a fabricated value.
    """

    follow_back_likelihood: int | None = None
    follow_back_confidence: float | None = None
    influence_score: int | None = None
    activity_score: int | None = None
    networking_score: int | None = None
    confidence: float | None = None
