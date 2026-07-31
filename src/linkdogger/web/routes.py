"""HTTP routes for the LinkDogger web interface."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from linkdogger.services.factory import VALID_PROVIDERS, build_people_service
from linkdogger.services.people_service import PeopleService
from linkdogger.services.processing import ResultFilters, SortKey

logger = logging.getLogger(__name__)

DEFAULT_SORT = "followback-desc"

# Bump when the bundled UI assets (css/js) change so browsers never
# serve a stale cached copy of the dashboard.
STATIC_VERSION = "2"


def register_routes(
    app: FastAPI, service: PeopleService, templates: Jinja2Templates
) -> None:
    """Attach the web routes to ``app``."""

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"static_version": STATIC_VERSION},
        )

    @app.get("/api/search")
    def api_search(
        company: str,
        sort: str = DEFAULT_SORT,
        role: str | None = None,
        location: str | None = None,
        limit: int | None = None,
        provider: str | None = None,
    ) -> dict:
        """Run a search through the shared application core."""
        if provider is not None and provider not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"invalid provider '{provider}' "
                f"(expected {', '.join(VALID_PROVIDERS)})",
            )

        # The web interface defaults to the configured discovery backend,
        # but lets the visitor pick a provider per search.
        search_service = service
        if provider is not None and provider != app.state.settings.discovery_backend:
            search_service = build_people_service(app.state.settings, provider=provider)

        try:
            sort_key = SortKey.from_option(sort)
        except ValueError:
            logger.warning("Ignoring invalid sort '%s'", sort)
            sort_key = None

        result = search_service.search_company(
            company,
            sort=sort_key,
            filters=ResultFilters(role=role, location=location),
            limit=limit,
        )
        return result.model_dump(mode="json")
