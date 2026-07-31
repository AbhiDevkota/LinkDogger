"""Follow-back likelihood estimation.

This is a prediction heuristic, NOT a factual statement. It must never
be presented as "this person will follow you back"; it is an estimate
based on publicly observable behavior.

Documented heuristic:

* For every platform with a public ``following`` count, compute the
  "generosity" ratio::

      following / (followers + following + 1)

  A high ratio means the account follows a large fraction of the
  network it attracts — such accounts tend to follow back more often.
  A low ratio (many followers, few follows) indicates selectivity.
* The platform with the most data drives the estimate.
* Verified accounts get a documented penalty: they are typically
  selective about whom they follow.
* Confidence is 0.85 when both follower and following counts are
  public, 0.5 when only partial data exists.
* With no public following data at all the estimate is ``None`` —
  unknown, never guessed.

The system has NOT been trained or validated against real follow-back
outcomes; these numbers are explicitly heuristics.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from pydantic import BaseModel

from linkdogger.models.social import SocialProfile


class FollowBackResult(BaseModel):
    """Follow-back likelihood estimate."""

    score: int | None = None
    confidence: float | None = None


class FollowBackScorer:
    """Estimates follow-back likelihood from public profile data."""

    VERIFIED_PENALTY = 0.9

    def calculate(self, profiles: Mapping[str, SocialProfile]) -> FollowBackResult:
        candidates: list[tuple[int, int, bool]] = []
        for profile in profiles.values():
            if profile.following is None:
                continue
            followers = profile.followers or 0
            candidates.append((followers, profile.following, bool(profile.verified)))

        if not candidates:
            return FollowBackResult(score=None, confidence=None)

        followers, following, verified = max(candidates, key=lambda c: c[0] + c[1])
        generosity = following / (followers + following + 1)
        score = round(100 * generosity)
        if verified:
            score = round(score * self.VERIFIED_PENALTY)

        confidence = 0.85 if followers > 0 and following > 0 else 0.5
        return FollowBackResult(score=score, confidence=confidence)


class InfluenceResult(BaseModel):
    """Public influence estimate derived from follower counts."""

    score: int | None = None
    confidence: float | None = None


class InfluenceScorer:
    """Log-scaled influence estimate from public follower counts.

    ``score = 100 * log10(1 + max_followers) / log10(1 + MAX_FOLLOWERS)``
    so 100 followers ~ 33, 10k followers ~ 67, 1M followers ~ 100.
    Returns ``None`` when no public follower count exists.
    """

    MAX_FOLLOWERS = 1_000_000

    def calculate(self, profiles: Mapping[str, SocialProfile]) -> InfluenceResult:
        followers = [
            profile.followers
            for profile in profiles.values()
            if profile.followers is not None
        ]
        if not followers:
            return InfluenceResult(score=None, confidence=None)

        max_followers = max(followers)
        score = round(
            100 * math.log10(1 + max_followers) / math.log10(1 + self.MAX_FOLLOWERS)
        )
        confidence = min(1.0, 0.4 + 0.15 * len(followers))
        return InfluenceResult(score=score, confidence=confidence)
