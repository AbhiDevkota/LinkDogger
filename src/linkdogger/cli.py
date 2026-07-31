"""LinkDogger command-line interface.

Stage 0 bootstrap: installable entry point with --version and --help.
The search command is introduced in a later stage.
"""

import typer

from linkdogger import __version__

app = typer.Typer(
    name="linkdogger",
    help="Public-profile people discovery and networking intelligence.",
    no_args_is_help=True,
)


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
