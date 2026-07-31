"""Rich table rendering for terminal output."""

from rich.table import Table

from linkdogger.models.search import SearchResult


def render_table(result: SearchResult) -> Table:
    """Render search results as a Rich table."""
    table = Table(title=f"Publicly discoverable people @ {result.query}")
    table.add_column("Name", style="bold", no_wrap=True)
    table.add_column("Position")
    table.add_column("Location")
    table.add_column("Platforms", justify="right")

    for person in result.results:
        table.add_row(
            person.name,
            person.position or "-",
            person.location or "-",
            ", ".join(sorted(person.profiles)) or "-",
        )

    return table
