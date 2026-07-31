"""LinkDogger command-line interface."""

import logging

import typer
from rich.console import Console

from linkdogger import __version__
from linkdogger.config.settings import get_settings
from linkdogger.discovery.mock import MockPeopleDiscoverer
from linkdogger.output.json import render_json
from linkdogger.output.table import render_table
from linkdogger.services.people_service import PeopleService

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="linkdogger",
    help="Public-profile people discovery and networking intelligence.",
    no_args_is_help=True,
)

console = Console()


def _build_people_service() -> PeopleService:
    """Build the application service.

    NOTE: currently wired to ``MockPeopleDiscoverer`` (clearly fictional
    sample data) until real company/people discovery lands in later
    stages. The CLI interface does not depend on this choice.
    """
    return PeopleService(MockPeopleDiscoverer())


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
    console.print(f"[bold]Company:[/bold] {result.query}")
    console.print(f"Found [bold]{result.count}[/bold] publicly discoverable people")
    console.print()
    console.print(render_table(result))
    console.print()
    console.print("[dim]Use --json for machine-readable output.[/dim]")
