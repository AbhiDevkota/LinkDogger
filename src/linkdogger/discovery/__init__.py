"""Discovery backends and interfaces."""

from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.discovery.mock import (
    MOCK_SOURCE,
    MockCompanyDiscoverer,
    MockPeopleDiscoverer,
)

__all__ = [
    "CompanyDiscoverer",
    "PeopleDiscoverer",
    "MOCK_SOURCE",
    "MockCompanyDiscoverer",
    "MockPeopleDiscoverer",
]
