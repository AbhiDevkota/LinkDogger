"""Package version consistency."""

import re

from linkdogger import __version__


def test_version_is_semver_like() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__) is not None


def test_version_is_non_empty() -> None:
    assert __version__.strip()


def test_module_entry_point_reports_version() -> None:
    from typer.testing import CliRunner

    from linkdogger.__main__ import app

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
