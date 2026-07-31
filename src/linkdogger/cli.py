"""LinkDogger command-line interface."""

import logging
from pathlib import Path

import typer
from rich.console import Console

from linkdogger import __version__
from linkdogger.config.settings import get_settings
from linkdogger.output.export import export_result
from linkdogger.output.json import render_json
from linkdogger.output.table import render_table
from linkdogger.services.factory import build_people_service
from linkdogger.services.people_service import PeopleService
from linkdogger.services.processing import ResultFilters, SortKey

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="linkdogger",
    help="Public-profile people discovery and networking intelligence.",
    invoke_without_command=True,
)

console = Console()


def _build_people_service() -> PeopleService:
    """Build the application service from the configured backend.

    Defaults to clearly marked sample data (mock backend) until the
    GitHub backend is configured via ``LINKDOGGER_DISCOVERY_BACKEND``.
    """
    return build_people_service(get_settings())


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"LinkDogger {__version__}")
        raise typer.Exit()


def _run_web() -> None:
    """Start the local web dashboard."""
    import uvicorn

    from linkdogger.web.app import create_app

    settings = get_settings()
    console.print("[bold cyan]LinkDogger[/bold cyan] web interface")
    console.print(
        f"Starting server at [bold]http://{settings.web_host}:{settings.web_port}[/bold]"
    )
    console.print("Press Ctrl+C to stop.")
    uvicorn.run(create_app(settings), host=settings.web_host, port=settings.web_port)


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the LinkDogger version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    web: bool = typer.Option(
        False,
        "--web",
        help="Launch the local web dashboard instead of the CLI.",
    ),
) -> None:
    """LinkDogger — public-profile people discovery and networking intelligence."""
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(levelname)s  %(message)s",
    )
    if web:
        _run_web()
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


@app.command()
def search(
    company: str = typer.Argument(..., help="Company name to search for."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    ),
    sort: str | None = typer.Option(
        None,
        "--sort",
        help=(
            "Sort results: followers, networking-score, followback, "
            "influence or name, each suffixed with -asc or -desc "
            "(e.g. followers-desc)."
        ),
    ),
    role: str | None = typer.Option(
        None, "--role", help="Only show people whose role matches this text."
    ),
    location: str | None = typer.Option(
        None, "--location", help="Only show people whose location matches this text."
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Maximum number of results to show."
    ),
    export: Path | None = typer.Option(  # noqa: B008 - typer.Option default, consistent with sibling options
        None, "--export", help="Write results to a file (.json, .csv or .md)."
    ),
) -> None:
    """Discover publicly discoverable people associated with COMPANY."""
    logger.info("Searching company: %s", company)

    sort_key: tuple[SortKey, str] | None = None
    if sort is not None:
        try:
            sort_key = SortKey.from_option(sort)
        except ValueError:
            raise typer.BadParameter(
                f"invalid sort '{sort}' (expected one of "
                "followers|networking-score|followback|influence|name "
                "suffixed with -asc or -desc)"
            ) from None

    filters = ResultFilters(role=role, location=location)
    result = _build_people_service().search_company(
        company, sort=sort_key, filters=filters, limit=limit
    )

    if export is not None:
        try:
            message = export_result(result, export)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from None
        console.print(f"[green]{message}[/green]")

    if json_output:
        console.print(render_json(result), markup=False)
        return

    console.print(f"[bold cyan]LinkDogger[/bold cyan] v{__version__}")
    if result.company is None:
        console.print(f"[bold red]Company not found:[/bold red] {result.query}")
        console.print("No company could be resolved from that query.")
        raise typer.Exit(code=1)

    console.print(f"[bold]Company:[/bold] {result.company.name}")
    if result.company.domain:
        console.print(f"[bold]Domain:[/bold] {result.company.domain}")
    console.print(f"Found [bold]{result.count}[/bold] publicly discoverable people")
    console.print()
    console.print(render_table(result))
    console.print()
    console.print("[dim]Use --json for machine-readable output.[/dim]")
