"""GitHub profile enrichment via the official GitHub REST API.

Fetches public user data (name, bio, location, followers, following,
blog/website, linked X/Twitter handle) for each candidate with a GitHub
username. Per-person failures are isolated: one bad profile never
destroys the run.

Email resolution is best-effort, tried in this order:

1. the public ``email`` field on the user profile;
2. the latest commit on the user's most recently updated public repo
   (``commit.author.email`` from the commits REST API);
3. the same commit's ``.patch`` endpoint
   (``https://github.com/{owner}/{repo}/commit/{sha}.patch``, the
   plain-text format ``git fetch`` uses) by parsing the ``From:``
   header;
4. the commit-search API — ``/search/commits`` matches the public
   commits authored by the username.

GitHub noreply addresses are dropped at every step, and any failure is
silently ignored: the person keeps no email rather than a guessed one.
The ``.patch`` lookup is skipped when
``LINKDOGGER_GITHUB_EMAIL_PATCH_TIMEOUT_SECONDS`` is unset or zero.
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
PATCH_FROM_PATTERN = re.compile(
    r"^From:\s+(?:[^<\n]*<)?([^<>\s@]+@[^<>\s@]+)>?",
    re.MULTILINE,
)
MAX_REPOS_TO_CHECK = 5


class GitHubEnricher:
    """Fills in person details from their public GitHub user profile."""

    name = "github"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = GitHubClient(settings, transport=transport)
        self._patch_timeout = settings.github_email_patch_timeout_seconds
        self._patch_client = httpx.Client(
            timeout=self._patch_timeout or 10.0,
            follow_redirects=True,
            transport=transport,
        )

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
        email = self._email_from_latest_commit(username)
        if not email:
            email = self._email_from_commit_search(username)
        if not email:
            return person
        return person.model_copy(update={"email": email})

    def _email_from_latest_commit(self, username: str) -> str | None:
        """Email from the latest commit on the user's most recent public repo.

        Returns ``None`` when the user has no public repo with a usable
        commit, or when every found address is a GitHub noreply address.
        """
        try:
            payload = self._client.get_json(
                f"/users/{username}/repos?sort=updated&per_page={MAX_REPOS_TO_CHECK}"
            )
        except LinkDoggerError as exc:
            logger.debug("Repo list skipped for %s: %s", username, exc)
            return None
        if not isinstance(payload, list):
            return None

        for repo in payload:
            if not isinstance(repo, dict) or repo.get("fork"):
                continue
            owner = (
                repo.get("owner", {}).get("login")
                if isinstance(repo.get("owner"), dict)
                else None
            )
            name = repo.get("name")
            if not owner or not name:
                continue
            try:
                commits = self._client.get_json(
                    f"/repos/{owner}/{name}/commits?per_page=1"
                )
            except LinkDoggerError as exc:
                logger.debug("Commit list skipped for %s/%s: %s", owner, name, exc)
                continue
            if not isinstance(commits, list) or not commits:
                continue
            commit = commits[0] if isinstance(commits[0], dict) else None
            if not isinstance(commit, dict):
                continue
            sha = commit.get("sha")
            author = commit.get("commit", {}).get("author", {})
            email = author.get("email") if isinstance(author, dict) else None
            if email and not email.endswith(NOREPLY_SUFFIX):
                return email
            if email and sha:
                email = self._email_from_patch(owner, name, str(sha))
                if email:
                    return email
        return None

    def _email_from_patch(self, owner: str, repo: str, sha: str) -> str | None:
        """Email from the ``From:`` header of the commit's public .patch."""
        timeout = self._patch_timeout
        if timeout is None or timeout <= 0:
            return None
        try:
            response = self._patch_client.get(
                f"https://github.com/{owner}/{repo}/commit/{sha}.patch",
            )
        except httpx.HTTPError as exc:
            logger.debug(".patch lookup failed for %s/%s: %s", owner, repo, exc)
            return None
        if response.status_code != 200:
            return None
        header = response.text.split("\n\n", 1)[0]
        match = PATCH_FROM_PATTERN.search(header)
        if match is None:
            return None
        email = match.group(1)
        if email.endswith(NOREPLY_SUFFIX):
            return None
        return email

    def _email_from_commit_search(self, username: str) -> str | None:
        """Email from the public commits authored by ``username``."""
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
            return None
        if not email or email.endswith(NOREPLY_SUFFIX):
            return None
        return email

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
