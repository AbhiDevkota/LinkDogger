"""Cross-platform identity matching.

Determines whether different profiles likely belong to the same person
using only publicly available signals:

* personal website cross-reference        (very strong)
* identical username across platforms     (strong)
* normalized full-name match              (strong)
* public cross-links (e.g. GitHub's X handle is materialized as an X
  profile by the enricher and then matched via username)
* same company field                      (weak, never sufficient alone)

Each pair is scored 0..1 and merged only when the score reaches the
merge threshold. Weak matches are deliberately NOT merged: it is better
to keep profiles separate than to attribute a profile to the wrong
person. Every merged profile records its ``identity_confidence``.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Sequence

from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

logger = logging.getLogger(__name__)

# Named thresholds (no unexplained magic numbers).
WEBSITE_MATCH_SCORE = 0.95
USERNAME_MATCH_SCORE = 0.9
NAME_MATCH_SCORE = 0.85
COMPANY_MATCH_SCORE = 0.35
MERGE_THRESHOLD = 0.7
MAX_CONFIDENCE = 0.98

_NAME_PATTERN = re.compile(r"[^a-z0-9]")


class IdentityMatcher:
    """Merges candidate profiles that likely belong to the same person."""

    def __init__(
        self,
        merge_threshold: float = MERGE_THRESHOLD,
        max_confidence: float = MAX_CONFIDENCE,
    ) -> None:
        self._merge_threshold = merge_threshold
        self._max_confidence = max_confidence

    def match_people(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        """Greedily cluster candidates by pairwise identity confidence."""
        merged: list[PersonProfile] = []
        for person in people:
            best_index: int | None = None
            best_score = 0.0
            for index, candidate in enumerate(merged):
                score = self._pair_confidence(person, candidate)
                if score > best_score:
                    best_index = index
                    best_score = score

            if best_index is not None and best_score >= self._merge_threshold:
                merged[best_index] = _merge_into(merged[best_index], person, best_score)
                logger.info(
                    "Merged profiles for %s into %s (confidence %.2f)",
                    person.name,
                    merged[best_index].name,
                    best_score,
                )
            else:
                merged.append(person)
        return merged

    def _pair_confidence(self, a: PersonProfile, b: PersonProfile) -> float:
        """Estimate the probability that ``a`` and ``b`` are the same person."""
        signals: list[float] = []

        website_a = a.profiles.get("website")
        website_b = b.profiles.get("website")
        if (
            website_a is not None
            and website_b is not None
            and _normalize_url(website_a.url) == _normalize_url(website_b.url)
        ):
            signals.append(WEBSITE_MATCH_SCORE)

        usernames_a = {p.username.lower() for p in a.profiles.values() if p.username}
        usernames_b = {p.username.lower() for p in b.profiles.values() if p.username}
        if usernames_a & usernames_b:
            signals.append(USERNAME_MATCH_SCORE)

        normalized_a = _normalize_name(a.name)
        normalized_b = _normalize_name(b.name)
        if normalized_a and normalized_a == normalized_b:
            signals.append(NAME_MATCH_SCORE)

        if a.company and a.company == b.company:
            signals.append(COMPANY_MATCH_SCORE)

        if not signals:
            return 0.0

        combined = 1.0 - math.prod(1.0 - signal for signal in signals)
        return min(combined, self._max_confidence)


def _merge_into(
    base: PersonProfile, other: PersonProfile, score: float
) -> PersonProfile:
    """Merge ``other`` into ``base``, recording ``score`` on new profiles."""
    profiles = dict(base.profiles)
    for platform, profile in other.profiles.items():
        existing = profiles.get(platform)
        if existing is None:
            profiles[platform] = profile.model_copy(
                update={"identity_confidence": score}
            )
            continue
        if (profile.confidence or 0.0) > (existing.confidence or 0.0):
            profiles[platform] = profile.model_copy(
                update={"identity_confidence": score}
            )

    name = _better_name(base.name, other.name, profiles)
    sources = sorted(set(base.sources) | set(other.sources))

    return base.model_copy(
        update={
            "name": name,
            "position": base.position or other.position,
            "location": base.location or other.location,
            "bio": base.bio or other.bio,
            "profiles": profiles,
            "sources": sources,
        }
    )


def _better_name(a: str, b: str, profiles: dict[str, SocialProfile]) -> str:
    usernames = {p.username.lower() for p in profiles.values() if p.username}
    a_is_login = a.strip().lower() in usernames
    b_is_login = b.strip().lower() in usernames
    if a_is_login and not b_is_login:
        return b
    if b_is_login and not a_is_login:
        return a
    return max(a, b, key=len)


def _normalize_name(name: str) -> str:
    """Normalize a full name for comparison (case/punctuation-insensitive)."""
    return _NAME_PATTERN.sub("", name.lower())


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/").lower()
