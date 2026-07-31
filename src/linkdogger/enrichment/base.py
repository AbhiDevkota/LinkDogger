"""Enrichment contracts."""

from collections.abc import Sequence
from typing import Protocol

from linkdogger.models.person import PersonProfile


class Enricher(Protocol):
    """Contract for enriching candidate people with public profile data.

    Implementations augment a person's profile with publicly available
    information from one source. One source failing must never destroy
    a search: enrichers isolate per-person failures and raise
    ``EnrichmentIncompleteError`` when some candidates were skipped.
    """

    name: str

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        """Enrich every person and return the updated list."""
