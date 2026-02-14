from pathlib import Path

from rich.console import Console
from rich.padding import Padding
from rich.theme import Theme

from machinate.settings import Settings
from machinate.templating import parse_frontmatter


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
        "active": "green",
    }
)


def get_console(settings: Settings) -> Console:  # noqa: ARG001  # pyright: ignore[reportUnusedParameter]
    return Console(theme=theme)


def print_files_with_summary(console: Console, files: list[Path], indent: int) -> None:
    """Print file paths with optional summary from frontmatter."""
    for f in files:
        meta, _ = parse_frontmatter(f.read_text())
        summary = meta.get("summary", "")
        console.print(f"{'  ' * indent}[path]{short_path(f)}[/path]")
        if summary:
            console.print(Padding(f"[muted]{summary}[/muted]", (0, 0, 0, indent * 2 + 2)))
