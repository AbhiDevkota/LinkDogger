"""LinkDogger command-line interface."""

import json
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


def _build_people_service(provider: str | None = None) -> PeopleService:
    """Build the application service for the selected provider."""
    return build_people_service(get_settings(), provider=provider)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"LinkDogger {__version__}")
        raise typer.Exit()


def _print_warnings(result: object) -> None:
    """Print non-fatal warnings collected during the search."""
    warnings = getattr(result, "warnings", None)
    if warnings:
        for warning in warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")


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
    log_output: bool = typer.Option(
        False,
        "--log",
        help="Show detailed search logs instead of the progress animation.",
    ),
    sort: str | None = typer.Option(
        None,
        "--sort",
        help=(
            "Sort results: followers, networking-score, followback, "
            "influence or name, each suffixed with -asc or -desc "
            "(e.g. followers-desc). Defaults to followback-desc."
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
    provider: str = typer.Option(
        "linkedin",
        "--provider",
        help="Data provider: linkedin (default), github, hybrid, or mock.",
    ),
    hybrid: bool = typer.Option(
        False,
        "--hybrid",
        help="Use GitHub and LinkedIn together (shortcut for --provider hybrid).",
    ),
    export: Path | None = typer.Option(  # noqa: B008 - typer.Option default, consistent with sibling options
        None, "--export", help="Write results to a file (.json, .csv or .md)."
    ),
) -> None:
    """Discover publicly discoverable people associated with COMPANY."""
    if not log_output:
        logging.getLogger().setLevel(logging.WARNING)

    if hybrid:
        provider = "hybrid"
    if provider not in ("linkedin", "github", "hybrid", "mock"):
        raise typer.BadParameter(
            f"invalid provider '{provider}' (expected linkedin, github, hybrid or mock)"
        )

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
    service = _build_people_service(provider)

    if log_output or json_output:
        result = service.search_company(
            company, sort=sort_key, filters=filters, limit=limit
        )
    else:
        with console.status(
            "[bold cyan]Searching[/bold cyan] for publicly discoverable people..."
        ):
            result = service.search_company(
                company, sort=sort_key, filters=filters, limit=limit
            )

    if export is not None:
        try:
            message = export_result(result, export)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from None
        console.print(f"[green]{message}[/green]")

    if json_output:
        console.print(render_json(result), markup=False, soft_wrap=True)
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
    if result.filtered_out_count > 0:
        console.print(
            f"[dim]{result.filtered_out_count} discovered profile(s) were "
            "excluded by your filters (e.g. --location, --role).[/dim]"
        )
    console.print()
    _print_warnings(result)
    console.print(render_table(result))
    console.print()
    console.print("[dim]Use --json for machine-readable output.[/dim]")


@app.command("linkedin-login")
def linkedin_login() -> None:
    """Save your LinkedIn session cookies for the LinkedIn provider.

    Log in once in your normal browser, then paste the ``li_at`` and
    ``JSESSIONID`` cookie values here. They are saved to the cookie file
    configured in ``LINKDOGGER_LINKEDIN_COOKIE_FILE`` and used by the
    LinkedIn provider (``open-linkedin-api``) instead of a password
    login — useful when LinkedIn challenges password logins. The file
    holds live session cookies: it is yours, never shared or committed.
    """
    settings = get_settings()
    cookie_file = settings.linkedin_cookie_file
    if not cookie_file:
        raise typer.BadParameter(
            "set LINKDOGGER_LINKEDIN_COOKIE_FILE first (see .env.example)"
        )
    console.print("[bold]Log in once in your normal browser:[/bold]")
    console.print("1. Open https://www.linkedin.com and log in as usual.")
    console.print("2. Press F12 (DevTools) → Application → Cookies → linkedin.com")
    console.print("3. Copy the values of the cookies [bold]li_at[/bold] and")
    console.print("   [bold]JSESSIONID[/bold].")
    console.print("4. Paste them below (they are only saved to your cookie file).")
    li_at = typer.prompt("li_at cookie value", hide_input=True)
    jsessionid = typer.prompt("JSESSIONID cookie value", hide_input=True)
    if not li_at.strip() or not jsessionid.strip():
        raise typer.BadParameter("cookie values cannot be empty")
    payload = {"li_at": li_at.strip(), "JSESSIONID": jsessionid.strip()}
    try:
        Path(cookie_file).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"could not write cookie file: {exc}") from None
    console.print(f"[green]Session cookies saved to {cookie_file}[/green]")
