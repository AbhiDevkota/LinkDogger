"""X (Twitter) enrichment adapter.

X does not offer an official public API for reading profiles without
authentication. LinkDogger therefore marks this source as unavailable
instead of scraping, bypassing anything, or guessing.
"""

from __future__ import annotations

from collections.abc import Sequence

from linkdogger.errors import SourceUnavailableError
from linkdogger.models.person import PersonProfile


class XEnricher:
    """Reports X/Twitter enrichment as unavailable."""

    name = "x"

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        raise SourceUnavailableError(
            "X has no official public profile API without authentication; "
            "X enrichment is unavailable"
        )
