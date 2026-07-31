"""Data models: defaults, nullability, serialization."""

from linkdogger.models.company import Company
from linkdogger.models.networking import NetworkingScore
from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SCHEMA_VERSION, SearchResult
from linkdogger.models.social import SocialProfile


def test_person_defaults_are_nullable() -> None:
    person = PersonProfile(name="Alice Example")
    assert person.company is None
    assert person.position is None
    assert person.location is None
    assert person.bio is None
    assert person.profiles == {}
    assert person.networking is None
    assert person.sources == []


def test_social_profile_defaults() -> None:
    profile = SocialProfile(
        platform="x", url="https://x.com/alice", username="alice", source="test"
    )
    assert profile.followers is None
    assert profile.following is None
    assert profile.verified is None
    assert profile.confidence is None
    assert profile.identity_confidence is None


def test_networking_score_defaults_to_all_null() -> None:
    score = NetworkingScore()
    assert score.follow_back_likelihood is None
    assert score.follow_back_confidence is None
    assert score.influence_score is None
    assert score.activity_score is None
    assert score.networking_score is None
    assert score.confidence is None


def test_search_result_defaults() -> None:
    result = SearchResult(
        query="Acme",
        generated_at=__import__("datetime").datetime(2026, 1, 1),
        count=0,
    )
    assert result.schema_version == SCHEMA_VERSION == "1.0"
    assert result.company is None
    assert result.results == []
    assert result.source_status == {}
    assert result.warnings == []


def test_person_serialization_keeps_nulls_not_fabricated() -> None:
    person = PersonProfile(name="Alice Example")
    data = person.model_dump()
    assert data["position"] is None
    assert data["location"] is None
    assert data["profiles"] == {}


def test_company_serialization_roundtrip() -> None:
    company = Company(
        name="Acme Corporation",
        aliases=["Acme"],
        domain="acme.com",
        description="Test co",
        source="test",
        resolved_from="acme",
    )
    restored = Company.model_validate(company.model_dump())
    assert restored == company
