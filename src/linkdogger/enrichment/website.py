"""Website reachability verification.

Verifies that a publicly listed personal website responds successfully.
Unreachable or slow sites are left flagged by their original source —
the URL is never fabricated and never silently dropped.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from linkdogger.config.settings import Settings
from linkdogger.errors import EnrichmentIncompleteError, NetworkTimeoutError
from linkdogger.models.person import PersonProfile

logger = logging.getLogger(__name__)


class WebsiteEnricher:
    """Checks reachability of personal website URLs."""

    name = "website"

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )
        self._settings = settings

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        skipped = 0
        for person in people:
            website = person.profiles.get("website")
            if website is None:
                continue
            try:
                response = self._client.head(website.url)
                if response.status_code >= 400:
                    skipped += 1
                    logger.info(
                        "Website %s returned %d; marked as unavailable",
                        website.url,
                        response.status_code,
                    )
            except httpx.TimeoutException as exc:
                raise NetworkTimeoutError(
                    f"Website check timed out: {website.url}"
                ) from exc
            except httpx.HTTPError as exc:
                skipped += 1
                logger.warning("Website check failed for %s: %s", website.url, exc)

        if skipped:
            raise EnrichmentIncompleteError(
                f"Website check failed for {skipped} URL(s)", skipped
            )
        return list(people)
