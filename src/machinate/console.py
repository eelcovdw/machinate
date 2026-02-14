from pathlib import Path

from rich.console import Console
from rich.theme import Theme

from machinate.settings import Settings


def short_path(path: Path) -> str:
    """Shorten a path: relative to cwd if possible, otherwise ~/..."""
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        pass
    try:
        return ("~" / path.relative_to(Path.home())).as_posix()
    except ValueError:
        return str(path)


theme = Theme(
    {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red bold",
        "muted": "dim",
        "path": "blue underline",
        "name": "bold magenta",
    }
)


def get_console(settings: Settings) -> Console:  # noqa: ARG001  # pyright: ignore[reportUnusedParameter]
    return Console(theme=theme)
