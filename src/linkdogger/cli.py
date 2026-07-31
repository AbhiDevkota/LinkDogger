"""LinkDogger command-line interface."""

import logging

import typer
from rich.console import Console

from linkdogger import __version__
from linkdogger.config.settings import get_settings
from linkdogger.output.json import render_json
from linkdogger.output.table import render_table
from linkdogger.services.factory import build_people_service
from linkdogger.services.people_service import PeopleService

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="linkdogger",
    help="Public-profile people discovery and networking intelligence.",
    no_args_is_help=True,
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


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the LinkDogger version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """LinkDogger — public-profile people discovery and networking intelligence."""
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(levelname)s  %(message)s",
    )


@app.command()
def search(
    company: str = typer.Argument(..., help="Company name to search for."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    ),
) -> None:
    """Discover publicly discoverable people associated with COMPANY."""
    logger.info("Searching company: %s", company)
    result = _build_people_service().search_company(company)

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
