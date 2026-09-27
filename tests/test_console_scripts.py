import json
import os
import subprocess
import sys
import tomllib
from importlib.metadata import entry_points, version
from pathlib import Path
from typing import cast

import pytest
from packaging.requirements import Requirement

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_console_scripts_point_at_app() -> None:
    scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}
    for name in ("machi", "machinate"):
        assert scripts.get(name) == "machinate.cli.cli:app"


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_console_script_smoke(executable: str) -> None:
    launcher = Path(sys.executable).with_name(executable)
    result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Usage" in result.stdout


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_console_script_reports_usage_errors(executable: str) -> None:
    """Exercise the leaf-command parse_args path that catches click.UsageError.

    Fresh resolution with Typer 0.26+ vendors Click, so typer raises its own
    vendored exceptions that the external click.UsageError handler would miss;
    a structured usage error proves the external Click is the one in use.
    """
    launcher = Path(sys.executable).with_name(executable)
    result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "info", "--definitely-not-an-option"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MACHI_FORMAT": "json"},
    )
    assert result.returncode == 2, result.stderr
    parsed = cast("dict[str, object]", json.loads(result.stderr))
    assert parsed["command"] == "info"
    assert "No such option" in str(parsed["error"])


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_console_script_reports_group_usage_errors(executable: str) -> None:
    """C5: group-level failures also use the structured formatter."""
    launcher = Path(sys.executable).with_name(executable)
    result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "oops"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "MACHI_AUTOMATION": "true"},
    )
    assert result.returncode == 2, result.stderr
    parsed = cast("dict[str, object]", json.loads(result.stderr))
    assert parsed["command"] == "task"
    assert "No such command 'oops'." in str(parsed["error"])


def test_installed_versions_satisfy_declared_constraints() -> None:
    """Catch a fresh resolution drifting outside the declared constraints (C1)."""
    with PYPROJECT.open("rb") as stream:
        dependencies = cast("list[str]", tomllib.load(stream)["project"]["dependencies"])
    for dependency in dependencies:
        requirement = Requirement(dependency)
        installed = version(requirement.name)
        assert installed in requirement.specifier, (
            f"Installed {requirement.name}=={installed} violates {requirement}"
        )


def test_click_is_external_not_vendored() -> None:
    """Typer 0.26+ vendors Click; importing it as typer._vendor.click breaks cli.py."""
    result = subprocess.run(  # noqa: S603 - interpreter with fixed arguments
        [sys.executable, "-c", "import click; print(click.__file__)"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    click_file = Path(result.stdout.strip()).resolve()
    assert "typer" not in click_file.parts
