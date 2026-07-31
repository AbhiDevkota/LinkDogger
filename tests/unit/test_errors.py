"""Error hierarchy."""

import pytest

from linkdogger.errors import (
    CompanyNotFoundError,
    EnrichmentIncompleteError,
    LinkDoggerError,
    NetworkTimeoutError,
    ProviderError,
    RateLimitError,
    SourceUnavailableError,
)

ALL_ERRORS = [
    CompanyNotFoundError,
    SourceUnavailableError,
    RateLimitError,
    ProviderError,
    NetworkTimeoutError,
    EnrichmentIncompleteError,
]


@pytest.mark.parametrize("error_type", ALL_ERRORS)
def test_all_errors_derive_from_base(error_type: type[LinkDoggerError]) -> None:
    assert issubclass(error_type, LinkDoggerError)
    assert issubclass(error_type, Exception)


def test_str_renders_message() -> None:
    assert str(ProviderError("bad response")) == "bad response"


def test_enrichment_incomplete_carries_skipped_count() -> None:
    error = EnrichmentIncompleteError("2 of 5 enriched", skipped=3)
    assert error.skipped == 3
    assert "2 of 5 enriched" in str(error)


def test_errors_are_catchable_by_base_type() -> None:
    with pytest.raises(LinkDoggerError):
        raise RateLimitError("calm down")
