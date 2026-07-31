"""Networking intelligence scoring."""

import pytest

from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile
from linkdogger.scoring.followback import FollowBackScorer, InfluenceScorer
from linkdogger.scoring.networking import NetworkingScorer
from linkdogger.scoring.weights import ScoringWeights


def _social(
    platform: str,
    followers: int | None,
    following: int | None,
    verified: bool | None = None,
) -> SocialProfile:
    return SocialProfile(
        platform=platform,
        url=f"https://example.com/{platform}",
        followers=followers,
        following=following,
        verified=verified,
        source="test",
    )


def _person(
    profiles: dict[str, SocialProfile], position: str | None = None
) -> PersonProfile:
    return PersonProfile(name="Test Person", position=position, profiles=profiles)


class TestScoringWeights:
    def test_default_weights_sum_to_one(self) -> None:
        weights = ScoringWeights()
        assert sum(weights.model_dump().values()) == pytest.approx(1.0)

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="must sum to 1.0"):
            ScoringWeights(professional_relevance=0.5)


class TestFollowBackScorer:
    def test_generous_account_scores_high(self) -> None:
        profiles = {"github": _social("github", followers=100, following=900)}
        result = FollowBackScorer().calculate(profiles)
        assert result.score is not None and result.score > 80
        assert result.confidence == 0.85

    def test_selective_account_scores_low(self) -> None:
        profiles = {"github": _social("github", followers=900, following=10)}
        result = FollowBackScorer().calculate(profiles)
        assert result.score is not None and result.score < 20

    def test_verified_account_is_penalized(self) -> None:
        base = FollowBackScorer().calculate(
            {"x": _social("x", followers=100, following=300, verified=False)}
        )
        verified = FollowBackScorer().calculate(
            {"x": _social("x", followers=100, following=300, verified=True)}
        )
        assert base.score is not None and verified.score is not None
        assert verified.score < base.score

    def test_no_following_data_returns_none(self) -> None:
        profiles = {"github": _social("github", followers=100, following=None)}
        result = FollowBackScorer().calculate(profiles)
        assert result.score is None
        assert result.confidence is None

    def test_partial_data_lowers_confidence(self) -> None:
        profiles = {"github": _social("github", followers=100, following=0)}
        result = FollowBackScorer().calculate(profiles)
        assert result.score == 0
        assert result.confidence == 0.5


class TestInfluenceScorer:
    def test_more_followers_more_influence(self) -> None:
        small = InfluenceScorer().calculate(
            {"x": _social("x", followers=100, following=None)}
        )
        large = InfluenceScorer().calculate(
            {"x": _social("x", followers=100_000, following=None)}
        )
        assert small.score is not None and large.score is not None
        assert large.score > small.score

    def test_no_follower_data_returns_none(self) -> None:
        profiles = {"github": _social("github", followers=None, following=None)}
        result = InfluenceScorer().calculate(profiles)
        assert result.score is None

    def test_one_million_followers_scores_100(self) -> None:
        result = InfluenceScorer().calculate(
            {"x": _social("x", followers=1_000_000, following=None)}
        )
        assert result.score == 100


class TestNetworkingScorer:
    def test_rich_profile_scores_within_range(self) -> None:
        person = _person(
            {
                "github": _social("github", followers=500, following=700),
                "x": _social("x", followers=2000, following=100),
            },
            position="Engineer",
        )
        result = NetworkingScorer().score(person)
        assert result.networking_score is not None
        assert 0 <= result.networking_score <= 100
        assert result.follow_back_likelihood is not None
        assert result.influence_score is not None
        assert result.confidence is not None

    def test_bare_profile_scores_none(self) -> None:
        person = _person({})
        result = NetworkingScorer().score(person)
        assert result.networking_score is None
        assert result.influence_score is None

    def test_custom_weights_are_respected(self) -> None:
        person = _person({"github": _social("github", followers=100, following=100)})
        influence_only = NetworkingScorer(
            weights=ScoringWeights(
                professional_relevance=0,
                public_activity=0,
                social_presence=0,
                influence=1.0,
                follow_back=0,
                profile_confidence=0,
            )
        )
        result = influence_only.score(person)
        assert result.networking_score == result.influence_score

    def test_position_boosts_relevance(self) -> None:
        scorer = NetworkingScorer()
        minimal = {"github": _social("github", followers=None, following=None)}
        with_role = scorer.score(_person(minimal, position="Engineer"))
        without_role = scorer.score(_person(minimal))
        assert with_role.networking_score is not None
        assert without_role.networking_score is not None
        assert with_role.networking_score > without_role.networking_score
