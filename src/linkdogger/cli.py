"""LinkDogger command-line interface."""

import json
import logging
import re
import time
from pathlib import Path

import typer
from rich.console import Console

from linkdogger import __version__
from linkdogger.config.settings import get_settings
from linkdogger.errors import IPCError, MailError, SourceUnavailableError
from linkdogger.ipc import IPCClient, IPCServer
from linkdogger.linkedin_api import get_linkedin_client, validate_session
from linkdogger.mail.sender import DEFAULT_BODY, DEFAULT_SUBJECT, send_emails_from_file
from linkdogger.mcp_server import serve as mcp_serve
from linkdogger.output.export import export_emails, export_result
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


def _slugify(value: str) -> str:
    """Turn a company/query name into a safe filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "results"


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
    export: str | None = typer.Option(  # noqa: B008 - typer.Option default, consistent with sibling options
        None,
        "--export",
        help=(
            "Write results to a file (.json, .csv or .md), or 'email' to "
            "export every found email address to a JSON file."
        ),
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
        if export == "email":
            slug = _slugify(result.company.name if result.company else result.query)
            message = export_emails(result, Path(f"{slug}.emails.json"))
        else:
            target = Path(export)
            try:
                message = export_result(result, target)
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


@app.command()
def serve() -> None:
    """Start the local web dashboard (same as ``linkdogger --web``)."""
    _run_web()


@app.command("ipc-serve")
def ipc_serve() -> None:
    """Start the local IPC server (JSON over localhost HTTP, for scripts)."""
    settings = get_settings()
    server = IPCServer(
        _build_people_service(),
        host=settings.ipc_host,
        port=settings.ipc_port,
        token=settings.ipc_token,
        backend=settings.discovery_backend,
    )
    console.print("[bold cyan]LinkDogger[/bold cyan] IPC server")
    console.print(
        f"Listening on [bold]http://{settings.ipc_host}:{settings.ipc_port}/rpc[/bold]"
    )
    if settings.ipc_token:
        console.print("Authentication token is enabled.")
    console.print("Press Ctrl+C to stop.")
    try:
        server.start()
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        console.print("[dim]IPC server stopped.[/dim]")


@app.command()
def ipc(
    method: str = typer.Argument(
        ...,
        help="Method to call: ping, status, search or export_emails.",
    ),
    company: str | None = typer.Option(
        None, "--company", "-c", help="Company name (search / export_emails)."
    ),
    provider: str = typer.Option(
        "linkedin",
        "--provider",
        help="Data provider: linkedin, github, hybrid, or mock.",
    ),
    sort: str | None = typer.Option(
        None, "--sort", help="Sort key (e.g. followers-desc, name-asc)."
    ),
    role: str | None = typer.Option(
        None, "--role", help="Only show people whose role matches this text."
    ),
    location: str | None = typer.Option(
        None, "--location", help="Only show people whose location matches this text."
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Maximum number of results."
    ),
) -> None:
    """Call a method on a running IPC server (see ``ipc-serve``)."""
    if method not in ("ping", "status", "search", "export_emails"):
        raise typer.BadParameter(
            f"unknown method '{method}' (expected ping, status, search "
            "or export_emails)"
        )
    if method in ("search", "export_emails") and not company:
        raise typer.BadParameter(f"--company is required for the '{method}' method")
    settings = get_settings()
    client = IPCClient(settings.ipc_host, settings.ipc_port, token=settings.ipc_token)
    try:
        if method == "ping":
            result = client.call("ping")
        elif method == "status":
            result = client.call("status")
        else:
            result = client.call(
                method,
                company=company,
                sort=sort,
                role=role,
                location=location,
                limit=limit,
                provider=provider,
            )
    except IPCError as exc:
        raise typer.BadParameter(str(exc)) from None
    console.print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command()
def mcp() -> None:
    """Run the MCP (Model Context Protocol) stdio server for AI clients."""
    error_console = Console(stderr=True)
    settings = get_settings()
    error_console.print(
        f"[dim]LinkDogger MCP server (v{__version__}) on stdio — "
        "speak JSON-RPC here.[/dim]"
    )
    code = mcp_serve(_build_people_service(), backend=settings.discovery_backend)
    raise typer.Exit(code)


@app.command()
def send(
    file: Path = typer.Argument(  # noqa: B008 - typer.Argument default, consistent with sibling options
        ..., help="Exported contacts file (e.g. from --export email)."
    ),
    subject: str | None = typer.Option(
        None,
        "--subject",
        help="Subject template; placeholders: {name}, {company}, {position}.",
    ),
    body: str | None = typer.Option(
        None, "--body", help="Body template (see --subject for placeholders)."
    ),
    body_file: Path | None = typer.Option(  # noqa: B008 - typer.Option default, consistent with sibling options
        None, "--body-file", help="Read the body template from a UTF-8 text file."
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Build and preview every message without connecting to SMTP.",
    ),
    delay: float = typer.Option(  # noqa: B008 - typer.Option default, consistent with sibling options
        1.0, "--delay", help="Seconds to wait between sends (0 to disable)."
    ),
) -> None:
    """Send personalized emails to every address in an exported contacts file.

    Configure the outbox with LINKDOGGER_SMTP_HOST (plus username,
    password and from-address) in your .env. Always try --dry-run first.
    """
    settings = get_settings()
    if body_file is not None:
        try:
            body = body_file.read_text(encoding="utf-8")
        except OSError as exc:
            raise typer.BadParameter(f"could not read body file: {exc}") from None
    subject = subject if subject is not None else DEFAULT_SUBJECT
    body = body if body is not None else DEFAULT_BODY

    if dry_run:
        console.print("[bold yellow]Dry run[/bold yellow] — no emails will be sent.")
    elif not settings.smtp_host:
        raise typer.BadParameter(
            "SMTP is not configured: set LINKDOGGER_SMTP_HOST (and "
            "LINKDOGGER_SMTP_USERNAME/PASSWORD/FROM) in your .env first"
        )

    try:
        report = send_emails_from_file(
            str(file),
            subject=subject,
            body=body,
            settings=settings,
            dry_run=dry_run,
            delay_seconds=delay,
        )
    except MailError as exc:
        raise typer.BadParameter(str(exc)) from None

    verb = "Previewed" if dry_run else "Sent"
    console.print(
        f"[bold cyan]LinkDogger[/bold cyan] {verb.lower()} {len(report.sent)} "
        f"of {report.total} emails"
    )
    if not dry_run:
        if report.sent:
            console.print("[green]Delivered to:[/green] " + ", ".join(report.sent))
        for email, error in report.failed:
            console.print(f"[red]Failed[/red] {email}: {error}")
    console.print(
        "[dim]Use --dry-run to preview messages before sending for real.[/dim]"
    )


def _linkedin_login() -> None:
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
    try:
        client = get_linkedin_client(
            None, None, cookie_file=cookie_file, validate=False
        )
    except SourceUnavailableError as exc:
        console.print(
            f"[yellow]Warning:[/yellow] cookies saved, but the session could "
            f"not be checked now: {exc}"
        )
        return
    summary = validate_session(client)
    if summary:
        console.print(
            f"[green]Session validated: {summary}[/green] — "
            "LinkedIn API access confirmed."
        )
    else:
        console.print(
            "[yellow]Warning:[/yellow] cookies saved, but LinkedIn did not "
            "confirm the session (it may be blocking automated access right "
            "now). Re-run this command later; searches will fall back to "
            "unverified results meanwhile."
        )


@app.command("login")
def login() -> None:
    """Save your LinkedIn session cookies (shortcut for ``linkedin-login``)."""
    _linkedin_login()


@app.command("linkedin-login")
def linkedin_login() -> None:
    """Save your LinkedIn session cookies.

    Log in once in your normal browser, then paste the ``li_at`` and
    ``JSESSIONID`` cookie values here. They are saved to the cookie file
    configured in ``LINKDOGGER_LINKEDIN_COOKIE_FILE`` and used by the
    LinkedIn provider (``open-linkedin-api``) instead of a password
    login — useful when LinkedIn challenges password logins. The file
    holds live session cookies: it is yours, never shared or committed.
    The saved session is validated with a live API call and the result
    is reported.
    """
    _linkedin_login()


def _redact(value: str | None) -> str:
    """Redact a secret for display (``set (abc***)`` or ``(not set)``)."""
    if not value:
        return "(not set)"
    return f"set ({value[:3]}***)"


@app.command()
def config() -> None:
    """Show the effective configuration (secrets are redacted)."""
    settings = get_settings()
    fields = [
        ("LINKDOGGER_DISCOVERY_BACKEND", settings.discovery_backend),
        ("LINKDOGGER_LOG_LEVEL", settings.log_level),
        ("LINKDOGGER_MAX_RESULTS", str(settings.max_results)),
        ("LINKDOGGER_WEB_HOST", settings.web_host),
        ("LINKDOGGER_WEB_PORT", str(settings.web_port)),
        ("LINKDOGGER_REQUEST_TIMEOUT_SECONDS", str(settings.request_timeout_seconds)),
        (
            "LINKDOGGER_GITHUB_EMAIL_PATCH_TIMEOUT_SECONDS",
            str(settings.github_email_patch_timeout_seconds),
        ),
        ("LINKDOGGER_GITHUB_TOKEN", _redact(settings.github_token)),
        ("LINKDOGGER_LINKEDIN_EMAIL", settings.linkedin_email or "(not set)"),
        ("LINKDOGGER_LINKEDIN_PASSWORD", _redact(settings.linkedin_password)),
        (
            "LINKDOGGER_LINKEDIN_COOKIES_DIR",
            settings.linkedin_cookies_dir or "(not set)",
        ),
        (
            "LINKDOGGER_LINKEDIN_COOKIE_FILE",
            settings.linkedin_cookie_file or "(not set)",
        ),
        ("LINKDOGGER_IPC_HOST", settings.ipc_host),
        ("LINKDOGGER_IPC_PORT", str(settings.ipc_port)),
        ("LINKDOGGER_IPC_TOKEN", _redact(settings.ipc_token)),
        ("LINKDOGGER_SMTP_HOST", settings.smtp_host or "(not set)"),
        ("LINKDOGGER_SMTP_PORT", str(settings.smtp_port)),
        ("LINKDOGGER_SMTP_USERNAME", settings.smtp_username or "(not set)"),
        ("LINKDOGGER_SMTP_PASSWORD", _redact(settings.smtp_password)),
        ("LINKDOGGER_SMTP_FROM", settings.smtp_from or "(not set)"),
        ("LINKDOGGER_SMTP_FROM_NAME", settings.smtp_from_name or "(not set)"),
        ("LINKDOGGER_IMAP_HOST", settings.imap_host or "(not set)"),
        ("LINKDOGGER_IMAP_PORT", str(settings.imap_port)),
        ("LINKDOGGER_IMAP_USERNAME", settings.imap_username or "(not set)"),
        ("LINKDOGGER_IMAP_PASSWORD", _redact(settings.imap_password)),
        ("LINKDOGGER_IMAP_FOLDER", settings.imap_folder),
    ]
    for name, value in fields:
        console.print(f"  [bold]{name}[/bold] = {value}")


@app.command()
def doctor() -> None:
    """Diagnose the installation: providers, credentials, and the LinkedIn session."""
    settings = get_settings()
    console.print("[bold cyan]LinkDogger[/bold cyan] diagnostics")
    console.print(f"  Version: {__version__}")
    console.print(f"  Log level: {settings.log_level}")
    console.print()
    console.print("[bold]Providers[/bold]")
    console.print("  [green]mock[/green]      available (offline sample data)")
    if settings.github_token:
        console.print("  github    token configured")
    else:
        console.print(
            "  github    [yellow]no token[/yellow] (set LINKDOGGER_GITHUB_TOKEN)"
        )
    console.print("  x         unavailable (no official public API)")
    linkedin_configured = bool(
        settings.linkedin_cookie_file
        or (settings.linkedin_email and settings.linkedin_password)
    )
    if settings.linkedin_cookie_file:
        console.print(f"  linkedin  cookie file: {settings.linkedin_cookie_file}")
    elif settings.linkedin_email and settings.linkedin_password:
        console.print("  linkedin  credentials configured (email login)")
    else:
        console.print(
            "  linkedin  [yellow]not configured[/yellow] (run `linkdogger "
            "login` or set LINKDOGGER_LINKEDIN_EMAIL/PASSWORD)"
        )
    if linkedin_configured:
        try:
            client = get_linkedin_client(
                settings.linkedin_email,
                settings.linkedin_password,
                settings.linkedin_cookies_dir,
                settings.linkedin_cookie_file,
                timeout=settings.request_timeout_seconds,
                validate=False,
            )
        except SourceUnavailableError as exc:
            console.print(f"  linkedin  [yellow]session check failed:[/yellow] {exc}")
        else:
            summary = validate_session(client)
            if summary:
                console.print(f"  linkedin  [green]session valid:[/green] {summary}")
            else:
                console.print(
                    "  linkedin  [yellow]session could not be validated[/yellow] "
                    "(LinkedIn may be blocking automated access right now)"
                )
    console.print()
    console.print("[bold]Web dashboard[/bold]")
    console.print(
        f"  Run `linkdogger serve` (http://{settings.web_host}:{settings.web_port})"
    )
