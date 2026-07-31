"""Result sorting and filtering."""

from linkdogger.models.networking import NetworkingScore
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile
from linkdogger.services.processing import (
    ResultFilters,
    SortKey,
    apply_filters,
    apply_sort,
)


def _social(
    platform: str, username: str, followers: int | None = None
) -> SocialProfile:
    return SocialProfile(
        platform=platform,
        url=f"https://example.com/{username}",
        username=username,
        followers=followers,
        source="test",
    )


def _person(
    name: str,
    position: str | None = None,
    location: str | None = None,
    followers: int | None = None,
    networking: NetworkingScore | None = None,
    platforms: tuple[str, ...] = ("github",),
) -> PersonProfile:
    return PersonProfile(
        name=name,
        position=position,
        location=location,
        profiles={p: _social(p, f"{p}_{name.lower()}", followers) for p in platforms},
        networking=networking,
    )


class TestSortKey:
    def test_parses_desc_default(self) -> None:
        key, order = SortKey.from_option("followers")
        assert key == SortKey.FOLLOWERS
        assert order == "desc"

    def test_parses_asc_and_desc(self) -> None:
        assert SortKey.from_option("followers-desc") == (SortKey.FOLLOWERS, "desc")
        assert SortKey.from_option("name-asc") == (SortKey.NAME, "asc")

    def test_rejects_unknown_key(self) -> None:
        try:
            SortKey.from_option("bogus")
        except ValueError:
            return
        raise AssertionError("expected ValueError")


class TestApplySort:
    def test_sorts_by_followers_desc(self) -> None:
        people = [
            _person("A", followers=10),
            _person("B", followers=500),
            _person("C", followers=100),
        ]
        sorted_people = apply_sort(people, SortKey.FOLLOWERS, "desc")
        assert [p.name for p in sorted_people] == ["B", "C", "A"]

    def test_sorts_by_followers_asc(self) -> None:
        people = [
            _person("A", followers=10),
            _person("B", followers=500),
        ]
        sorted_people = apply_sort(people, SortKey.FOLLOWERS, "asc")
        assert [p.name for p in sorted_people] == ["A", "B"]

    def test_sorts_by_name_asc(self) -> None:
        people = [_person("Beta"), _person("Alpha")]
        sorted_people = apply_sort(people, SortKey.NAME, "asc")
        assert [p.name for p in sorted_people] == ["Alpha", "Beta"]

    def test_sorts_by_networking_score(self) -> None:
        people = [
            _person("A", networking=NetworkingScore(networking_score=40)),
            _person("B", networking=NetworkingScore(networking_score=90)),
        ]
        sorted_people = apply_sort(people, SortKey.NETWORKING_SCORE, "desc")
        assert [p.name for p in sorted_people] == ["B", "A"]

    def test_unknown_values_sort_last(self) -> None:
        people = [
            _person("A", networking=None),
            _person("B", networking=NetworkingScore(networking_score=90)),
        ]
        sorted_people = apply_sort(people, SortKey.NETWORKING_SCORE, "desc")
        assert [p.name for p in sorted_people] == ["B", "A"]


class TestApplyFilters:
    def test_filters_by_role(self) -> None:
        people = [
            _person("A", position="Software Engineer"),
            _person("B", position="Product Designer"),
        ]
        filtered = apply_filters(people, ResultFilters(role="engineer"))
        assert [p.name for p in filtered] == ["A"]

    def test_filters_by_location(self) -> None:
        people = [
            _person("A", location="San Francisco, CA"),
            _person("B", location="London, UK"),
        ]
        filtered = apply_filters(people, ResultFilters(location="san francisco"))
        assert [p.name for p in filtered] == ["A"]

    def test_filters_by_platform(self) -> None:
        people = [
            _person("A", platforms=("github",)),
            _person("B", platforms=("x", "github")),
        ]
        filtered = apply_filters(people, ResultFilters(platform="x"))
        assert [p.name for p in filtered] == ["B"]

    def test_filters_by_min_followers(self) -> None:
        people = [
            _person("A", followers=100),
            _person("B", followers=None),
        ]
        filtered = apply_filters(people, ResultFilters(min_followers=50))
        assert [p.name for p in filtered] == ["A"]

    def test_filters_by_min_score(self) -> None:
        people = [
            _person("A", networking=NetworkingScore(networking_score=70)),
            _person("B", networking=NetworkingScore(networking_score=30)),
        ]
        filtered = apply_filters(people, ResultFilters(min_score=50))
        assert [p.name for p in filtered] == ["A"]

    def test_no_active_filters_keeps_all(self) -> None:
        people = [_person("A"), _person("B")]
        assert apply_filters(people, ResultFilters()) == people

    def test_combined_filters_are_anded(self) -> None:
        people = [
            _person("A", position="Engineer", location="London, UK"),
            _person("B", position="Engineer", location="Berlin"),
        ]
        filtered = apply_filters(
            people, ResultFilters(role="engineer", location="berlin")
        )
        assert [p.name for p in filtered] == ["B"]
