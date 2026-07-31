"""Overall networking score.

Blends documented component scores into a single 0-100 estimate using
the weights from ``linkdogger.scoring.weights``. Components with no
data are excluded and remaining weights renormalized; when nothing is
known the score is ``None`` (unknown, never guessed).
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Mapping

from linkdogger.models.networking import NetworkingScore
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile
from linkdogger.scoring.followback import FollowBackScorer, InfluenceScorer
from linkdogger.scoring.weights import ScoringWeights

logger = logging.getLogger(__name__)

KNOWN_ROLE_SCORE = 85
UNKNOWN_ROLE_SCORE = 40
BIO_ACTIVITY_SCORE = 30
SOURCE_ACTIVITY_SCORE = 20
SOURCE_ACTIVITY_CAP = 70
PRESENCE_PER_PROFILE = 25
FALLBACK_PROFILE_CONFIDENCE = 0.5
FALLBACK_NETWORKING_CONFIDENCE = 0.6


class NetworkingScorer:
    """Computes the overall networking score for a person."""

    def __init__(
        self,
        weights: ScoringWeights | None = None,
        follow_back_scorer: FollowBackScorer | None = None,
        influence_scorer: InfluenceScorer | None = None,
    ) -> None:
        self._weights = weights or ScoringWeights()
        self._follow_back_scorer = follow_back_scorer or FollowBackScorer()
        self._influence_scorer = influence_scorer or InfluenceScorer()

    def score(self, person: PersonProfile) -> NetworkingScore:
        if not person.profiles:
            return NetworkingScore()

        follow_back = self._follow_back_scorer.calculate(person.profiles)
        influence = self._influence_scorer.calculate(person.profiles)

        components: dict[str, float | None] = {
            "professional_relevance": self._relevance(person),
            "public_activity": self._activity(person),
            "social_presence": self._presence(person.profiles),
            "influence": influence.score,
            "follow_back": follow_back.score,
            "profile_confidence": self._profile_confidence(person.profiles),
        }

        used_weights = 0.0
        weighted_total = 0.0
        for name, component in components.items():
            if component is None:
                continue
            weight = getattr(self._weights, name)
            used_weights += weight
            weighted_total += weight * component

        if used_weights == 0.0:
            return NetworkingScore(
                follow_back_likelihood=follow_back.score,
                follow_back_confidence=follow_back.confidence,
                influence_score=influence.score,
                activity_score=components["public_activity"],
                networking_score=None,
                confidence=None,
            )

        networking_score = round(weighted_total / used_weights)
        confidence = self._overall_confidence(
            person, follow_back.confidence, influence.confidence
        )
        return NetworkingScore(
            follow_back_likelihood=follow_back.score,
            follow_back_confidence=follow_back.confidence,
            influence_score=influence.score,
            activity_score=components["public_activity"],
            networking_score=networking_score,
            confidence=confidence,
        )

    @staticmethod
    def _relevance(person: PersonProfile) -> float:
        """Professional relevance: how clearly the role is known."""
        return KNOWN_ROLE_SCORE if person.position else UNKNOWN_ROLE_SCORE

    @staticmethod
    def _activity(person: PersonProfile) -> float:
        """Public activity proxy: bio presence + distinct public sources."""
        score = 0.0
        if person.bio:
            score += BIO_ACTIVITY_SCORE
        score += min(SOURCE_ACTIVITY_CAP, SOURCE_ACTIVITY_SCORE * len(person.sources))
        return score

    @staticmethod
    def _presence(profiles: Mapping[str, SocialProfile]) -> float:
        """Social presence: how many public profiles carry usable data."""
        with_data = sum(
            1
            for profile in profiles.values()
            if profile.followers is not None or profile.username
        )
        return min(100.0, PRESENCE_PER_PROFILE * with_data)

    @staticmethod
    def _profile_confidence(profiles: Mapping[str, SocialProfile]) -> float:
        confidences = [
            confidence
            for profile in profiles.values()
            if (confidence := profile.confidence) is not None
        ]
        identity_confidences = [
            confidence
            for profile in profiles.values()
            if (confidence := profile.identity_confidence) is not None
        ]
        all_confidences = confidences + identity_confidences
        if not all_confidences:
            return FALLBACK_PROFILE_CONFIDENCE * 100
        return statistics.mean(all_confidences) * 100

    def _overall_confidence(
        self,
        person: PersonProfile,
        follow_back_confidence: float | None,
        influence_confidence: float | None,
    ) -> float:
        confidences = [
            value for value in (follow_back_confidence, influence_confidence) if value
        ]
        profile_confidence = self._profile_confidence(person.profiles) / 100
        confidences.append(profile_confidence)
        if not confidences:
            return FALLBACK_NETWORKING_CONFIDENCE
        return round(statistics.mean(confidences), 2)
