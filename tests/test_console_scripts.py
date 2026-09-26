import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest


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
