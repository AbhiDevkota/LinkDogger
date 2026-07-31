"""Cross-platform identity matching."""

from linkdogger.matching.identity import (
    MERGE_THRESHOLD,
    IdentityMatcher,
)
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

MATCHER = IdentityMatcher()


def _profile(platform: str, username: str, source: str = "test") -> SocialProfile:
    return SocialProfile(
        platform=platform,
        url=f"https://example.com/{username}",
        username=username,
        source=source,
    )


def _person(
    name: str,
    profiles: dict[str, SocialProfile],
    company: str = "OpenAI",
) -> PersonProfile:
    return PersonProfile(
        name=name, company=company, profiles=profiles, sources=["test"]
    )


def test_identical_username_across_platforms_merges() -> None:
    alice_github = _person("Alice Example", {"github": _profile("github", "alice_dev")})
    alice_x = _person("Alice Example", {"x": _profile("x", "alice_dev")})

    people = MATCHER.match_people([alice_github, alice_x])

    assert len(people) == 1
    assert set(people[0].profiles) == {"github", "x"}
    assert people[0].profiles["x"].identity_confidence >= MERGE_THRESHOLD


def test_same_website_merges() -> None:
    a = _person(
        "Alice Example",
        {
            "github": _profile("github", "alice_dev"),
            "website": SocialProfile(
                platform="website", url="https://alice.example.com", source="test"
            ),
        },
    )
    b = _person(
        "Alice Other",
        {
            "x": _profile("x", "aliceother"),
            "website": SocialProfile(
                platform="website", url="https://alice.example.com/", source="test"
            ),
        },
    )

    people = MATCHER.match_people([a, b])

    assert len(people) == 1
    assert people[0].profiles["x"].identity_confidence is not None


def test_company_only_match_does_not_merge() -> None:
    a = _person("Alice Example", {"github": _profile("github", "alice_dev")})
    b = _person("Bob Example", {"github": _profile("github", "bob_dev")})

    people = MATCHER.match_people([a, b])

    assert len(people) == 2
    assert people[0].profiles["github"].identity_confidence is None


def test_unrelated_people_do_not_merge() -> None:
    a = _person("Alice Example", {"github": _profile("github", "alice_dev")})
    b = _person("Bob Different", {"x": _profile("x", "bobdiff")})

    people = MATCHER.match_people([a, b])

    assert len(people) == 2


def test_full_name_preferred_over_login() -> None:
    login = _person("alice-dev", {"github": _profile("github", "alice-dev")})
    named = _person("Alice Example", {"x": _profile("x", "alice_dev")})

    people = MATCHER.match_people([login, named])

    assert len(people) == 2  # no shared username/name signals -> no merge
    assert people[0].name == "alice-dev"


def test_merge_picks_full_name_when_signals_match() -> None:
    login = _person(
        "alice-dev",
        {"github": _profile("github", "alice_dev"), "website": _website()},
    )
    named = _person(
        "Alice Example",
        {"x": _profile("x", "alice_dev"), "website": _website()},
    )

    people = MATCHER.match_people([login, named])

    assert len(people) == 1
    assert people[0].name == "Alice Example"


def _website() -> SocialProfile:
    return SocialProfile(
        platform="website", url="https://alice.example.com", source="test"
    )


def test_merged_profile_keeps_biographical_data() -> None:
    a = _person(
        "Alice Example",
        {"github": _profile("github", "alice_dev")},
        company="OpenAI",
    )
    b = PersonProfile(
        name="Alice Example",
        company="OpenAI",
        location="Berlin",
        bio="ML engineer",
        profiles={"x": _profile("x", "alice_dev")},
        sources=["test2"],
    )

    people = MATCHER.match_people([a, b])

    assert len(people) == 1
    assert people[0].location == "Berlin"
    assert people[0].bio == "ML engineer"
    assert people[0].sources == sorted({"test", "test2"})
