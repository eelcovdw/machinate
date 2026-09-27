import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path


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
