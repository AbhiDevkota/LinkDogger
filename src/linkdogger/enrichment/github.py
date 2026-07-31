"""GitHub profile enrichment via the official GitHub REST API.

Fetches public user data (name, bio, location, followers, following,
blog/website, linked X/Twitter handle) for each candidate with a GitHub
username. Per-person failures are isolated: one bad profile never
destroys the run.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from linkdogger.config.settings import Settings
from linkdogger.discovery.github import GitHubClient
from linkdogger.errors import (
    EnrichmentIncompleteError,
    LinkDoggerError,
    ProviderError,
    RateLimitError,
)
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

logger = logging.getLogger(__name__)

SOURCE = "github-api"


class GitHubEnricher:
    """Fills in person details from their public GitHub user profile."""

    name = "github"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = GitHubClient(settings, transport=transport)

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        enriched: list[PersonProfile] = []
        skipped = 0
        for person in people:
            profile = person.profiles.get("github")
            if profile is None or not profile.username:
                enriched.append(person)
                continue
            try:
                user = self._client.get_json(f"/users/{profile.username}")
                if not isinstance(user, dict):
                    raise ProviderError(
                        f"Malformed GitHub user response for {profile.username}"
                    )
                enriched.append(self._apply_user(person, user))
            except RateLimitError:
                raise
            except LinkDoggerError as exc:
                skipped += 1
                logger.warning("GitHub enrichment skipped for %s: %s", person.name, exc)
                enriched.append(person)

        if skipped:
            raise EnrichmentIncompleteError(
                f"GitHub enrichment skipped {skipped} profile(s)", skipped
            )
        return enriched

    @staticmethod
    def _apply_user(person: PersonProfile, user: dict) -> PersonProfile:
        github = person.profiles["github"]
        github = github.model_copy(
            update={
                "followers": user.get("followers"),
                "following": user.get("following"),
                "confidence": 0.95,
            }
        )
        profiles = {**person.profiles, "github": github}

        blog = user.get("blog")
        has_website = "website" in profiles
        if blog and blog.startswith(("http://", "https://")) and not has_website:
            profiles["website"] = SocialProfile(
                platform="website",
                url=blog,
                source=SOURCE,
                confidence=0.9,
            )

        twitter = user.get("twitter_username")
        if twitter and "x" not in profiles:
            profiles["x"] = SocialProfile(
                platform="x",
                url=f"https://x.com/{twitter}",
                username=twitter,
                source=SOURCE,
                confidence=0.8,
            )

        sources = list(person.sources)
        if SOURCE not in sources:
            sources.append(SOURCE)

        return person.model_copy(
            update={
                "name": user.get("name") or person.name,
                "bio": user.get("bio") or person.bio,
                "location": user.get("location") or person.location,
                "profiles": profiles,
                "sources": sources,
            }
        )
