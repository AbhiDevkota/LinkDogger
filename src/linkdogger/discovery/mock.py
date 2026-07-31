"""Mock people discovery.

MOCK IMPLEMENTATION — returns clearly fictional sample data.

This exists so the CLI pipeline can be developed and tested before
real company/people discovery is implemented in later stages. It is
isolated behind ``PeopleDiscoverer`` and will be replaced without
touching the CLI interface.
"""

from linkdogger.discovery.base import PeopleDiscoverer
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

MOCK_SOURCE = "mock-sample-data"


class MockPeopleDiscoverer(PeopleDiscoverer):
    """Returns static sample people for a small set of known companies."""

    KNOWN_COMPANIES = frozenset({"acme", "globex", "openai"})

    def discover_people(self, company: str) -> list[PersonProfile]:
        if not company.strip() or company.strip().lower() not in self.KNOWN_COMPANIES:
            return []
        return self._sample_people(company.strip())

    @staticmethod
    def _sample_people(company: str) -> list[PersonProfile]:
        """Build clearly fictional sample profiles for ``company``."""
        return [
            PersonProfile(
                name="Alex Sample",
                company=company,
                position="Software Engineer",
                location="San Francisco, CA",
                profiles={
                    "linkedin": SocialProfile(
                        platform="linkedin",
                        url="https://www.linkedin.com/in/alex-sample",
                        username="alex-sample",
                        followers=1250,
                        source=MOCK_SOURCE,
                        confidence=0.99,
                    ),
                    "github": SocialProfile(
                        platform="github",
                        url="https://github.com/alexsample",
                        username="alexsample",
                        followers=340,
                        source=MOCK_SOURCE,
                        confidence=0.99,
                    ),
                },
                sources=[MOCK_SOURCE],
            ),
            PersonProfile(
                name="Jordan Sample",
                company=company,
                position="Product Designer",
                location=None,
                profiles={
                    "linkedin": SocialProfile(
                        platform="linkedin",
                        url="https://www.linkedin.com/in/jordan-sample",
                        username="jordan-sample",
                        followers=780,
                        source=MOCK_SOURCE,
                        confidence=0.99,
                    ),
                },
                sources=[MOCK_SOURCE],
            ),
            PersonProfile(
                name="Taylor Sample",
                company=company,
                position="Research Scientist",
                location="London, UK",
                profiles={
                    "github": SocialProfile(
                        platform="github",
                        url="https://github.com/taylorsample",
                        username="taylorsample",
                        followers=960,
                        source=MOCK_SOURCE,
                        confidence=0.98,
                    ),
                    "x": SocialProfile(
                        platform="x",
                        url="https://x.com/taylorsample",
                        username="taylorsample",
                        followers=5200,
                        source=MOCK_SOURCE,
                        confidence=0.98,
                    ),
                },
                sources=[MOCK_SOURCE],
            ),
        ]
