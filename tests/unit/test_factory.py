"""Service factory wiring."""

import pytest

from linkdogger.config.settings import Settings
from linkdogger.services.factory import VALID_PROVIDERS, build_people_service


def test_factory_defaults_to_mock_backend() -> None:
    service = build_people_service(Settings(_env_file=None))
    result = service.search_company("Acme")
    assert result.company is not None
    assert result.count > 0
    assert result.results[0].sources == ["mock-sample-data"]


def test_factory_builds_github_backend_service() -> None:
    service = build_people_service(Settings(_env_file=None, discovery_backend="github"))
    assert service is not None


def test_factory_builds_linkedin_provider_service() -> None:
    service = build_people_service(
        Settings(
            _env_file=None,
            linkedin_email="me@acme.com",
            linkedin_password="pw",
        ),
        provider="linkedin",
    )
    assert service is not None


def test_factory_builds_hybrid_provider_service() -> None:
    service = build_people_service(
        Settings(_env_file=None, discovery_backend="mock"), provider="hybrid"
    )
    assert service is not None


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        build_people_service(Settings(_env_file=None), provider="bogus")


def test_valid_providers_are_known() -> None:
    assert set(VALID_PROVIDERS) == {"linkedin", "github", "hybrid", "mock"}
