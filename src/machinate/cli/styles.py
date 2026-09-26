"""Central definitions for text-output styling.

Rich style strings live here so colors and emphasis are declared once and can be
tuned in one place. An empty style string means "render with no style".
"""

from typing import Final

HEADING: Final = "bold"
LABEL: Final = "bold"
PROJECT: Final = "bold"
MUTED: Final = "dim"
PATH: Final = "cyan"
TIMESTAMP: Final = "dim"
ERROR: Final = "bold red"

# Status badges are shared by plans and tasks; the same key means the same color.
STATUS_STYLES: Final[dict[str, str]] = {
    "draft": "dim",
    "active": "green",
    "done": "blue",
    "todo": "yellow",
    "in-progress": "cyan",
}
UNKNOWN_STATUS: Final = ""


def status_style(status: str) -> str:
    """Return the style for a status badge; empty for an unknown status."""
    return STATUS_STYLES.get(status, UNKNOWN_STATUS)
