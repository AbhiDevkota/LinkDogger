"""LinkedIn enrichment adapter.

LinkedIn does not offer an official public API for reading profiles
without authentication. LinkDogger therefore marks this source as
unavailable instead of scraping, bypassing anything, or guessing.
"""

from __future__ import annotations

from collections.abc import Sequence

from linkdogger.errors import SourceUnavailableError
from linkdogger.models.person import PersonProfile


class LinkedInEnricher:
    """Reports LinkedIn enrichment as unavailable."""

    name = "linkedin"

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        raise SourceUnavailableError(
            "LinkedIn has no official public profile API; "
            "LinkedIn enrichment is unavailable"
        )
