"""Networking signal data model."""

from pydantic import BaseModel


class NetworkingScore(BaseModel):
    """Networking-related signals for a person.

    Scores are heuristics and predictions, not factual statements.
    """

    follow_back_likelihood: int | None = None
    influence_score: int | None = None
    activity_score: int | None = None
    confidence: float | None = None
