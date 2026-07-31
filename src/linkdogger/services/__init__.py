"""Application services."""

from linkdogger.services.factory import build_people_service
from linkdogger.services.people_service import PeopleService

__all__ = ["PeopleService", "build_people_service"]
