"""Application exception hierarchy.

All errors raised by LinkDogger derive from ``LinkDoggerError`` so callers
can catch one base type. One failing source must never destroy an entire
search; adapters raise granular errors that the service layer catches and
converts into warnings / source status instead of aborting.
"""


class LinkDoggerError(Exception):
    """Base class for all LinkDogger errors."""


class CompanyNotFoundError(LinkDoggerError):
    """No company could be resolved for the given query."""


class SourceUnavailableError(LinkDoggerError):
    """A data source is unavailable (no API, disabled, unreachable)."""


class RateLimitError(LinkDoggerError):
    """A provider rate limit was reached. LinkDogger never circumvents it."""


class ProviderError(LinkDoggerError):
    """A provider returned an unexpected or malformed response."""


class NetworkTimeoutError(LinkDoggerError):
    """A provider request timed out."""
