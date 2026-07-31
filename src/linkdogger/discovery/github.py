"""GitHub discovery via the official GitHub REST API.

Only public data is used, through the official API, without
authentication when no token is configured. Rate limits are respected:
on 429/403 the client waits for the provider's ``Retry-After`` (capped)
and retries once; it never circumvents or evades rate limits.
"""

from __future__ import annotations

import logging
import time

import httpx

from linkdogger.config.settings import Settings
from linkdogger.discovery.base import CompanyDiscoverer, PeopleDiscoverer
from linkdogger.errors import (
    LinkDoggerError,
    NetworkTimeoutError,
    ProviderError,
    RateLimitError,
)
from linkdogger.models.company import Company
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
MAX_RETRY_WAIT_SECONDS = 5.0
MAX_RETRIES = 1


def _extract_retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After")
    try:
        return min(float(raw or 0.0), MAX_RETRY_WAIT_SECONDS)
    except ValueError:
        return 0.0


class GitHubClient:
    """Thin, rate-limit-aware wrapper around the GitHub REST API."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self._client = httpx.Client(
            base_url=GITHUB_API_BASE,
            headers=headers,
            timeout=settings.request_timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def get_json(self, path: str) -> dict | list:
        """GET ``path`` and return parsed JSON.

        Raises:
            RateLimitError: provider rate limit reached (never evaded).
            NetworkTimeoutError: request timed out.
            ProviderError: transport or HTTP errors, malformed responses.
        """
        last_error: LinkDoggerError | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.get(path)
            except httpx.TimeoutException as exc:
                last_error = NetworkTimeoutError(f"GitHub request timed out: {path}")
                logger.warning("GitHub timeout on %s (attempt %d)", path, attempt + 1)
                if attempt < MAX_RETRIES:
                    continue
                raise last_error from exc
            except httpx.HTTPError as exc:
                last_error = ProviderError(f"GitHub transport error on {path}: {exc}")
                logger.warning("GitHub transport error on %s: %s", path, exc)
                if attempt < MAX_RETRIES:
                    continue
                raise last_error from exc

            if response.status_code in (403, 429):
                wait = _extract_retry_after(response)
                if attempt < MAX_RETRIES and wait > 0:
                    logger.info("GitHub rate limited on %s; waiting %.1fs", path, wait)
                    time.sleep(wait)
                    continue
                raise RateLimitError(f"GitHub rate limit reached for {path}")

            if response.status_code == 404:
                raise ProviderError(f"GitHub resource not found: {path}")
            if response.status_code >= 400:
                raise ProviderError(
                    f"GitHub error {response.status_code} for {path}: "
                    f"{response.text[:200]}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise ProviderError(f"Malformed GitHub response for {path}") from exc

        error = last_error or ProviderError(f"GitHub request failed: {path}")
        raise error


class GitHubCompanyDiscoverer(CompanyDiscoverer):
    """Resolves companies via GitHub's official organization search."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = GitHubClient(settings, transport=transport)

    def resolve_company(self, query: str) -> Company | None:
        from urllib.parse import quote

        if not query.strip():
            return None
        search_path = f"/search/users?q={quote(query)} type:org&per_page=5"
        payload = self._client.get_json(search_path)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProviderError("Malformed GitHub organization search response")

        for item in payload["items"][:3]:
            login = item.get("login")
            if not login:
                continue
            org = self._client.get_json(f"/orgs/{login}")
            if not isinstance(org, dict):
                continue
            name = org.get("name") or org.get("login")
            return Company(
                name=name,
                aliases=[org.get("login")] if org.get("login") else [],
                domain=_domain_from_url(org.get("blog")),
                description=org.get("description"),
                source="github-api",
                resolved_from=query,
            )
        return None


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    domain = url.strip().lower().removeprefix("https://").removeprefix("http://")
    domain = domain.split("/")[0].split("?")[0]
    return domain or None


class GitHubPeopleDiscoverer(PeopleDiscoverer):
    """Discovers people whose public GitHub profile names ``company``.

    Uses the official Search Users API with the ``company:`` qualifier.
    Only the public company field is matched; private or hidden data is
    never accessed. Results are candidates: their identity is validated
    and enriched in later pipeline stages.
    """

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = GitHubClient(settings, transport=transport)

    def discover_people(self, company: Company) -> list[PersonProfile]:
        from urllib.parse import quote

        query = quote(f'company:"{company.name}"')
        search_path = f"/search/users?q={query}&per_page=30"
        payload = self._client.get_json(search_path)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ProviderError("Malformed GitHub user search response")

        people: list[PersonProfile] = []
        for item in payload["items"]:
            login = item.get("login")
            if not login or item.get("type") == "Organization":
                continue
            people.append(
                PersonProfile(
                    name=login,
                    company=company.name,
                    position=None,
                    profiles={
                        "github": SocialProfile(
                            platform="github",
                            url=f"https://github.com/{login}",
                            username=login,
                            source="github-api",
                            identity_confidence=None,
                        )
                    },
                    sources=["github-api"],
                )
            )
        return people
