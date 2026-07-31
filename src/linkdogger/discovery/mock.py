"""Mock company and people discovery.

MOCK IMPLEMENTATION — returns clearly fictional sample data.

This exists so the application can be developed and tested before real
discovery backends land. It is isolated behind the discovery protocols
and is replaced by the GitHub backend (``discovery/github.py``) when
``LINKDOGGER_DISCOVERY_BACKEND=github`` is configured.
"""

from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

MOCK_SOURCE = "mock-sample-data"


class MockCompanyDiscoverer(CompanyDiscoverer):
    """Resolves queries against a small static catalog of companies.

    Returns ``None`` for unknown queries so the service can report
    "company not found" honestly instead of guessing.
    """

    CATALOG: dict[str, Company] = {
        "acme": Company(
            name="Acme Corporation",
            aliases=["Acme", "Acme Corp"],
            domain="acme.com",
            source=MOCK_SOURCE,
            resolved_from="acme",
        ),
        "globex": Company(
            name="Globex Corporation",
            aliases=["Globex", "Globex Corp"],
            domain="globex.example",
            source=MOCK_SOURCE,
            resolved_from="globex",
        ),
        "openai": Company(
            name="OpenAI",
            aliases=["Open AI"],
            domain="openai.com",
            source=MOCK_SOURCE,
            resolved_from="openai",
        ),
    }

    def resolve_company(self, query: str) -> Company | None:
        key = query.strip().lower()
        return self.CATALOG.get(key)


class MockPeopleDiscoverer(PeopleDiscoverer):
    """Returns static sample people for a resolved company.

    Sample data is clearly fictional and marked with ``MOCK_SOURCE``.
    """

    def discover_people(self, company: Company) -> list[PersonProfile]:
        if not company.name.strip():
            return []
        return self._sample_people(company.name)

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
                        following=800,
                        source=MOCK_SOURCE,
                        confidence=0.99,
                    ),
                    "github": SocialProfile(
                        platform="github",
                        url="https://github.com/alexsample",
                        username="alexsample",
                        followers=340,
                        following=510,
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
                        following=90,
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
                        following=30,
                        source=MOCK_SOURCE,
                        confidence=0.98,
                    ),
                    "x": SocialProfile(
                        platform="x",
                        url="https://x.com/taylorsample",
                        username="taylorsample",
                        followers=5200,
                        following=210,
                        verified=True,
                        source=MOCK_SOURCE,
                        confidence=0.98,
                    ),
                },
                sources=[MOCK_SOURCE],
            ),
        ]
