"""Discovery contracts."""

from collections.abc import Sequence
from typing import Protocol

from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile


class CompanyDiscoverer(Protocol):
    """Contract for resolving a company query into a known company entity.

    Real implementations (static catalog, provider APIs) land behind this
    protocol; the service layer depends only on this interface.
    """

    def resolve_company(self, query: str) -> Company | None:
        """Resolve ``query`` to a ``Company`` or ``None`` when not found."""


class PeopleDiscoverer(Protocol):
    """Contract for discovering people associated with a company.

    The CLI and services depend only on this protocol, never on a
    concrete implementation.
    """

    def discover_people(self, company: Company) -> Sequence[PersonProfile]:
        """Return publicly discoverable people for ``company``."""
