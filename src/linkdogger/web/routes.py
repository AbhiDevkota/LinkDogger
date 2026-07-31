"""HTTP routes for the LinkDogger web interface."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from linkdogger.services.people_service import PeopleService
from linkdogger.services.processing import ResultFilters, SortKey

logger = logging.getLogger(__name__)

DEFAULT_SORT = "followback-desc"


def register_routes(
    app: FastAPI, service: PeopleService, templates: Jinja2Templates
) -> None:
    """Attach the web routes to ``app``."""

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request, name="index.html", context={}
        )

    @app.get("/api/search")
    def api_search(
        company: str,
        sort: str = DEFAULT_SORT,
        role: str | None = None,
        location: str | None = None,
        limit: int | None = None,
    ) -> dict:
        """Run a search through the shared application core."""
        try:
            sort_key = SortKey.from_option(sort)
        except ValueError:
            logger.warning("Ignoring invalid sort '%s'", sort)
            sort_key = None

        result = service.search_company(
            company,
            sort=sort_key,
            filters=ResultFilters(role=role, location=location),
            limit=limit,
        )
        return result.model_dump(mode="json")
