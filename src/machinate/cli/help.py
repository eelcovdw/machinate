"""Plain help sections for Machinate's Typer commands.

Typer hardcodes a bordered ``rich`` panel around every help section. Machinate's output is
deliberately plain, so the section titles render as headings instead. Typer exposes no hook for
that, so the panel is swapped for the duration of a single help render and restored immediately.
The replacement is process-global while it is in place, so a concurrent help render by another Typer
app in the same process could pick it up; Machinate serialises its own renders with a lock and
otherwise leaves other Typer apps untouched.
"""

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import cast

from rich.console import Group as RenderGroup
from rich.console import RenderableType
from rich.padding import Padding
from rich.text import Text
from typer import rich_utils

from . import styles

_SWAP_LOCK = threading.Lock()

# Typer's help sections read the panel class from this dictionary, and offers no hook to replace it.
_HELP_GLOBALS = cast("dict[str, object]", cast("object", vars(rich_utils)))


def _plain_panel(
    renderable: RenderableType, *, title: str | None = None, **_: object
) -> RenderableType:
    """Render a help section's title as a heading instead of drawing a box around it."""
    if title is None:
        return renderable
    return RenderGroup(Text(f"\n{title}", style=styles.HEADING), Padding(renderable, (0, 0, 0, 2)))


@contextmanager
def plain_help_sections() -> Generator[None]:
    """Render Typer's help sections as plain headings while the block runs."""
    with _SWAP_LOCK:
        original = _HELP_GLOBALS["Panel"]
        _HELP_GLOBALS["Panel"] = _plain_panel
        try:
            yield
        finally:
            _HELP_GLOBALS["Panel"] = original
