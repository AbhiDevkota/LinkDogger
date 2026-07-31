"""Rich table rendering for terminal output."""

from rich.table import Table

from linkdogger.models.person import PersonProfile
from linkdogger.models.search import SearchResult

ACCOUNT_ORDER = ("linkedin", "github", "x", "website")


def render_table(result: SearchResult) -> Table:
    """Render search results as a Rich table."""
    table = Table(title=f"Publicly discoverable people @ {result.query}")
    table.add_column("Name", style="bold", no_wrap=True)
    table.add_column("Position")
    table.add_column("Location")
    table.add_column("Email")
    table.add_column("Accounts")
    table.add_column("Followers", justify="right")
    table.add_column("Network", justify="right")
    table.add_column("Follow-back", justify="right")

    for person in result.results:
        followers = _max_followers(person)
        networking = person.networking
        network = (
            str(networking.networking_score)
            if networking and networking.networking_score
            else "-"
        )
        table.add_row(
            person.name,
            person.position or "-",
            person.location or "-",
            person.email or "-",
            _account_links(person),
            _format_followers(followers),
            network,
            _format_percent(
                networking.follow_back_likelihood
                if networking and networking.follow_back_likelihood is not None
                else None
            ),
        )

    return table


def _account_links(person: PersonProfile) -> str:
    """Render the person's public accounts as clickable links."""
    links = []
    for platform in ACCOUNT_ORDER:
        profile = person.profiles.get(platform)
        if profile is None or not profile.url:
            continue
        label = "X" if platform == "x" else platform
        links.append(f"[link={profile.url}]{label}[/link]")
    return " ".join(links) if links else "-"


def _max_followers(person: PersonProfile) -> int | None:
    counts = [
        profile.followers
        for profile in person.profiles.values()
        if profile.followers is not None
    ]
    return max(counts) if counts else None


def _format_followers(count: int | None) -> str:
    if count is None:
        return "-"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def _format_percent(value: int | None) -> str:
    return "-" if value is None else f"{value}%"
