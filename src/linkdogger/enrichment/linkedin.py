"""LinkedIn enrichment via the optional ``open-linkedin-api`` library.

``open-linkedin-api`` is a synchronous HTTP client for LinkedIn's Voyager
API (the same endpoints the web app uses). It authenticates with your own
LinkedIn account credentials and caches the session cookies, so LinkDogger
treats LinkedIn as an *opt-in source*:

* credentials are provided only by you, via environment variables
  (``LINKDOGGER_LINKEDIN_EMAIL`` / ``LINKDOGGER_LINKEDIN_PASSWORD``);
* the library's cookie cache (``LINKDOGGER_LINKEDIN_COOKIES_DIR``) keeps
  the session alive without re-logging in on every run;
* the library sleeps 2-5 seconds between requests to respect LinkedIn's
  rate limits; LinkDogger never attempts to bypass them;
* nothing is fetched unless a person already has a known LinkedIn
  profile (e.g. found in a public GitHub bio).

Without the library or credentials this source honestly reports
``unavailable`` instead of guessing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from linkdogger.config.settings import Settings
from linkdogger.errors import EnrichmentIncompleteError, SourceUnavailableError
from linkdogger.linkedin_api import (
    get_linkedin_client,
    get_linkedin_errors,
    get_profile,
)
from linkdogger.models.person import PersonProfile
from linkdogger.models.social import SocialProfile

logger = logging.getLogger(__name__)

SOURCE = "linkedin-api"


class LinkedInEnricher:
    """Enriches people who already have a LinkedIn profile."""

    name = "linkedin"

    def __init__(self, settings: Settings | None = None) -> None:
        self._email = settings.linkedin_email if settings else None
        self._password = settings.linkedin_password if settings else None
        self._cookies_dir = settings.linkedin_cookies_dir if settings else None
        self._cookie_file = settings.linkedin_cookie_file if settings else None
        self._timeout = settings.request_timeout_seconds if settings else None
        self._client: Any | None = None

    def enrich_all(self, people: Sequence[PersonProfile]) -> list[PersonProfile]:
        targets = [p for p in people if self._linkedin_profile(p) is not None]
        if not targets:
            return list(people)

        client = self._client or get_linkedin_client(
            self._email,
            self._password,
            self._cookies_dir,
            self._cookie_file,
            timeout=self._timeout,
        )
        self._client = client
        challenge_error, unauthorized_error = get_linkedin_errors()

        skipped = 0
        for person in targets:
            profile = self._linkedin_profile(person)
            assert profile is not None
            try:
                if not self._enrich_person(client, person, profile):
                    skipped += 1
            except (challenge_error, unauthorized_error) as exc:
                raise SourceUnavailableError(
                    f"LinkedIn session ended during enrichment: {exc}"
                ) from exc
            except Exception as exc:  # noqa: BLE001 - per-person isolation
                logger.warning("LinkedIn enrichment failed for %s: %s", profile, exc)
                skipped += 1
        if skipped:
            raise EnrichmentIncompleteError(
                f"LinkedIn skipped {skipped} profile(s) (not found or failed)",
                skipped,
            )
        return list(people)

    def _enrich_person(
        self, client: Any, person: PersonProfile, profile: SocialProfile
    ) -> bool:
        """Enrich one person; return ``False`` when the profile was skipped."""
        public_id, urn_id = _profile_ids(profile)
        data = get_profile(client, public_id=public_id, urn_id=urn_id)
        if not data:
            logger.info("LinkedIn profile not found or private: %s", profile)
            return False
        self._apply_profile(person, profile, data, public_id, urn_id)
        if person.email is None:
            contact = client.get_profile_contact_info(
                public_id=public_id, urn_id=urn_id
            )
            email = (contact or {}).get("email_address")
            if email:
                person.email = email
        return True

    def _apply_profile(
        self,
        person: PersonProfile,
        profile: SocialProfile,
        data: dict[str, Any],
        public_id: str | None,
        urn_id: str | None,
    ) -> None:
        """Copy profile data without overwriting known data."""
        first = data.get("firstName")
        last = data.get("lastName")
        if first and last and not person.name:
            person.name = f"{first} {last}"
        if data.get("headline") and not person.position:
            person.position = data["headline"]
        if data.get("locationName") and not person.location:
            person.location = data["locationName"]
        if data.get("summary") and not person.bio:
            person.bio = data["summary"]
        public_id = data.get("public_id") or public_id
        if public_id:
            profile.username = public_id
            if not profile.url:
                profile.url = f"https://www.linkedin.com/in/{public_id}/"
        if SOURCE not in person.sources:
            person.sources.append(SOURCE)

    @staticmethod
    def _linkedin_profile(person: PersonProfile) -> SocialProfile | None:
        profile = person.profiles.get("linkedin")
        if profile and (profile.url or profile.username):
            return profile
        return None


def _profile_ids(profile: SocialProfile) -> tuple[str | None, str | None]:
    """Extract ``(public_id, urn_id)`` from a linkedin profile reference."""
    public_id: str | None = None
    if profile.url:
        public_id = profile.url.rstrip("/").rsplit("/", 1)[-1]
    if public_id:
        return public_id, None
    username = profile.username
    if username and username.isdigit():
        return None, username
    return username, None
