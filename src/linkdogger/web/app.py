"""FastAPI application factory for the LinkDogger web interface.

The web interface consumes the exact same ``PeopleService`` as the CLI
(see ``linkdogger.services.factory``); no business logic is duplicated.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from linkdogger.config.settings import Settings, get_settings
from linkdogger.services.factory import build_people_service
from linkdogger.web.routes import register_routes

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the LinkDogger web application."""
    settings = settings or get_settings()
    service = build_people_service(settings)

    app = FastAPI(
        title="LinkDogger",
        description="Public-profile people discovery and networking intelligence.",
        version="1.0",
    )
    app.state.service = service
    app.state.settings = settings

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    register_routes(app, service, templates)
    return app
