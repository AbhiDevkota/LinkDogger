"""Networking scoring weights — the single source of truth.

Every score in the application is a documented heuristic, never a
factual measurement. It summarizes publicly observable signals and is
always labeled as an estimate. Weights are collected here (instead of
being scattered as magic numbers) so the whole scoring behavior can be
reviewed and adjusted in one place.

Overall networking score components and their weights (must sum to 1.0):

* professional_relevance — how clearly the person's professional role
  is known (e.g. a public position/title).
* public_activity — signals of public activity: a public bio and the
  number of distinct public sources attached to the profile.
* social_presence — how many public profiles carry usable data.
* influence — log-scaled public follower count across platforms.
* follow_back — estimated follow-back likelihood (see
  ``linkdogger.scoring.followback`` for the documented heuristic).
* profile_confidence — average public confidence of the matched
  profiles (including identity-matching confidence).

Unknown components are excluded and the remaining weights are
renormalized, so a person with sparse data still gets an honest score
with a lower overall confidence.
"""

from pydantic import BaseModel, model_validator


class ScoringWeights(BaseModel):
    """Weights of each networking-score component (must sum to 1.0)."""

    professional_relevance: float = 0.15
    public_activity: float = 0.15
    social_presence: float = 0.20
    influence: float = 0.25
    follow_back: float = 0.15
    profile_confidence: float = 0.10

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "ScoringWeights":
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1.0, got {total}")
        return self
