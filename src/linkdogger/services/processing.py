"""Result sorting and filtering.

Shared by the CLI and the web GUI so both interfaces sort and filter
identically. The filter set is a Pydantic model and intentionally
future-ready: role, location, platform, followers, score and confidence
filters can all be enabled by adding fields here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from linkdogger.models.person import PersonProfile


class SortKey(StrEnum):
    """Supported sort keys, each combined with an order by the CLI/GUI."""

    FOLLOWERS = "followers"
    NETWORKING_SCORE = "networking-score"
    FOLLOWBACK = "followback"
    INFLUENCE = "influence"
    NAME = "name"

    @classmethod
    def from_option(cls, value: str) -> tuple[SortKey, Literal["asc", "desc"]]:
        """Parse ``<key>-<asc|desc>`` (default order: descending)."""
        if value.endswith("-asc"):
            return cls(value[: -len("-asc")]), "asc"
        if value.endswith("-desc"):
            return cls(value[: -len("-desc")]), "desc"
        return cls(value), "desc"


class ResultFilters(BaseModel):
    """Filters applied to search results before sorting."""

    role: str | None = Field(default=None, description="Substring match on position.")
    location: str | None = Field(
        default=None, description="Substring match on location."
    )
    platform: str | None = Field(
        default=None, description="Require this platform profile."
    )
    min_followers: int | None = Field(
        default=None, description="Minimum public followers."
    )
    min_score: int | None = Field(default=None, description="Minimum networking score.")
    min_confidence: float | None = Field(
        default=None, description="Minimum networking confidence."
    )


def apply_filters(
    people: list[PersonProfile], filters: ResultFilters
) -> list[PersonProfile]:
    """Return only the people matching every active filter."""
    result = people
    if filters.role:
        needle = filters.role.lower()
        result = [p for p in result if p.position and needle in p.position.lower()]
    if filters.location:
        needle = filters.location.lower()
        result = [p for p in result if p.location and needle in p.location.lower()]
    if filters.platform:
        result = [p for p in result if filters.platform in p.profiles]
    if filters.min_followers is not None:
        result = [
            p
            for p in result
            if (count := _max_followers(p)) is not None
            and count >= filters.min_followers
        ]
    if filters.min_score is not None:
        result = [
            p
            for p in result
            if p.networking is not None
            and p.networking.networking_score is not None
            and p.networking.networking_score >= filters.min_score
        ]
    if filters.min_confidence is not None:
        result = [
            p
            for p in result
            if p.networking is not None
            and p.networking.confidence is not None
            and p.networking.confidence >= filters.min_confidence
        ]
    return result


def apply_sort(
    people: list[PersonProfile], key: SortKey, order: str
) -> list[PersonProfile]:
    """Sort people by ``key`` in the requested order.

    People whose sort value is unknown sort last regardless of order —
    unknown is never silently treated as zero.
    """
    sorters = {
        SortKey.FOLLOWERS: lambda p: _max_followers(p),
        SortKey.NETWORKING_SCORE: lambda p: _networking_field(p, "networking_score"),
        SortKey.FOLLOWBACK: lambda p: _networking_field(p, "follow_back_likelihood"),
        SortKey.INFLUENCE: lambda p: _networking_field(p, "influence_score"),
        SortKey.NAME: lambda p: p.name.lower(),
    }
    sorter = sorters[key]
    with_value = [p for p in people if sorter(p) is not None]
    without_value = [p for p in people if sorter(p) is None]
    reverse = order == "desc"
    with_value.sort(key=sorter, reverse=reverse)
    return with_value + without_value


def _networking_field(person: PersonProfile, field: str) -> int | None:
    if person.networking is None:
        return None
    return getattr(person.networking, field)


def _max_followers(person: PersonProfile) -> int | None:
    counts = [
        profile.followers
        for profile in person.profiles.values()
        if profile.followers is not None
    ]
    return max(counts) if counts else None
