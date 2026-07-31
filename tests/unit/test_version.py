"""Package version consistency."""

import re

from linkdogger import __version__


def test_version_is_semver_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__) is not None


def test_version_is_non_empty() -> None:
    assert __version__.strip()
