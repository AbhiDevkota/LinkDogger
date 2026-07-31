"""Discovery contracts."""

from collections.abc import Sequence
from typing import Protocol

from linkdogger.models.person import PersonProfile


class PeopleDiscoverer(Protocol):
    """Contract for discovering people associated with a company.

    Real implementations (company resolution, public profile discovery)
    land in later stages; the CLI and services depend only on this
    protocol, never on a concrete implementation.
    """

    def discover_people(self, company: str) -> Sequence[PersonProfile]:
        """Return publicly discoverable people for ``company``."""
