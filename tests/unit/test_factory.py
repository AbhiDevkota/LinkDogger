"""Service factory wiring."""

from linkdogger.config.settings import Settings
from linkdogger.services.factory import build_people_service


def test_factory_defaults_to_mock_backend() -> None:
    service = build_people_service(Settings(_env_file=None))
    result = service.search_company("Acme")
    assert result.company is not None
    assert result.count > 0
    assert result.results[0].sources == ["mock-sample-data"]


def test_factory_builds_github_backend_service() -> None:
    service = build_people_service(Settings(_env_file=None, discovery_backend="github"))
    assert service is not None
