"""GitHub profile enrichment via the official GitHub REST API.

Fetches public user data (name, bio, location, followers, following,
blog/website, linked X/Twitter handle) for each candidate with a GitHub
username. Per-person failures are isolated: one bad profile never
destroys the run.

Email resolution is best-effort: the public ``email`` field first, then
the commit-history method — the official commit search API matches the
public commits authored by the username and reads the address the user
themselves published. GitHub noreply addresses are dropped, and any
failure in this fallback is silently ignored.
"""

from __future__ import annotations

import logging
import re
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

COMMITS_SEARCH_ACCEPT = "application/vnd.github.cloak-preview+json"
LINKEDIN_BIO_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/([A-Za-z0-9_-]+)"
)
NOREPLY_SUFFIX = "@users.noreply.github.com"


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
                person = self._apply_user(person, user)
                person = self._resolve_email(person)
                enriched.append(person)
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

    def _resolve_email(self, person: PersonProfile) -> PersonProfile:
        """Fill ``person.email`` from public data, best-effort."""
        if person.email:
            return person
        username = person.profiles["github"].username
        if not username:
            return person
        try:
            payload = self._client.get_json(
                f"/search/commits?q=author:{username}&per_page=1",
                accept=COMMITS_SEARCH_ACCEPT,
            )
            items = payload.get("items") if isinstance(payload, dict) else None
            email = (
                items[0].get("commit", {}).get("author", {}).get("email")
                if items
                else None
            )
        except LinkDoggerError as exc:
            logger.debug("Commit-email lookup skipped for %s: %s", username, exc)
            return person
        if not email or email.endswith(NOREPLY_SUFFIX):
            return person
        return person.model_copy(update={"email": email})

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

        linkedin = _linkedin_from_bio(user.get("bio"))
        if linkedin and "linkedin" not in profiles:
            profiles["linkedin"] = SocialProfile(
                platform="linkedin",
                url=f"https://www.linkedin.com/in/{linkedin}",
                username=linkedin,
                source=SOURCE,
                confidence=0.7,
            )

        sources = list(person.sources)
        if SOURCE not in sources:
            sources.append(SOURCE)

        public_email = user.get("email")
        if public_email and public_email.endswith(NOREPLY_SUFFIX):
            public_email = None

        return person.model_copy(
            update={
                "name": user.get("name") or person.name,
                "bio": user.get("bio") or person.bio,
                "location": user.get("location") or person.location,
                "email": public_email or person.email,
                "profiles": profiles,
                "sources": sources,
            }
        )


def _linkedin_from_bio(bio: str | None) -> str | None:
    if not bio:
        return None
    match = LINKEDIN_BIO_PATTERN.search(bio)
    return match.group(1) if match else None
