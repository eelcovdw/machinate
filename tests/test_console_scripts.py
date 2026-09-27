import subprocess
import sys
import tomllib
from importlib.metadata import entry_points, version
from pathlib import Path
from typing import cast

from packaging.requirements import Requirement

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_console_scripts_point_at_app() -> None:
    scripts = {entry.name: entry.value for entry in entry_points(group="console_scripts")}
    for name in ("machi", "machinate"):
        assert scripts.get(name) == "machinate.cli.cli:app"


def test_console_script_smoke() -> None:
    """The installed launcher exists and reaches the app (wiring is checked above)."""
    launcher = Path(sys.executable).with_name("machi")
    result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Usage" in result.stdout


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
