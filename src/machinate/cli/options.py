"""Shared CLI option definitions.

Every option used by more than one command is declared here once, as an ``Annotated``
alias. Command modules import the alias; only options whose choices genuinely differ per
resource (status) have more than one alias.
"""

from pathlib import Path
from typing import Annotated, Literal

import click
import typer

from machinate.models.documents import PlanStatus, TaskStatus

from .dependencies import get_dependencies


def validate_output_format(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Reject unknown formatter names as a usage error, keeping custom formatters usable."""
    if value is None:
        return None
    names = get_dependencies(ctx).formatters
    if value not in names:
        choices = ", ".join(sorted(names))
        message = f"{value!r} is not a known formatter; choose from {choices}."
        raise click.BadParameter(message, ctx=ctx, param=param, param_hint="'--format'")
    return value


OUTPUT_FORMAT = Annotated[
    str | None,
    typer.Option(
        "--format",
        callback=validate_output_format,
        help="Formatter name (text or json by default).",
    ),
]

PROJECT = Annotated[
    Path | None,
    typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
]

PLAN = Annotated[
    str | None,
    typer.Option("--plan", "-p", help="Plan to use; otherwise the current plan."),
]

TAGS = Annotated[
    list[str] | None,
    typer.Option("--tag", help="Tag(s) to apply. Repeat for multiple tags."),
]

MATCH_TAGS = Annotated[
    list[str] | None,
    typer.Option("--tag", help="Match any tag. Repeat for multiple tags."),
]

SUMMARY = Annotated[
    str | None,
    typer.Option("--summary", help="Summary text; pass an empty string to clear it."),
]

CLEAR_TAGS = Annotated[
    bool,
    typer.Option("--clear-tags", help="Remove all tags; mutually exclusive with --tag."),
]

PLAN_STATUS = Annotated[
    Literal["draft", "active", "done"] | None,
    typer.Option("--status", help="Status: draft, active, or done."),
]

TASK_STATUS = Annotated[
    Literal["todo", "in-progress", "done"] | None,
    typer.Option("--status", help="Status: todo, in-progress, or done."),
]

PLAN_STATUS_FILTER = Annotated[
    list[PlanStatus] | None,
    typer.Option(
        "--status",
        help="Match any status: draft, active, done. Repeat for multiple statuses.",
        click_type=click.Choice(["draft", "active", "done"]),
    ),
]

TASK_STATUS_FILTER = Annotated[
    list[TaskStatus] | None,
    typer.Option(
        "--status",
        help="Match any status: todo, in-progress, done. Repeat for multiple statuses.",
        click_type=click.Choice(["todo", "in-progress", "done"]),
    ),
]

SORT = Annotated[
    Literal["name", "created_at", "modified_at"],
    typer.Option(help="Sort by name, created_at, or modified_at."),
]

PLAN_SORT = Annotated[
    Literal["name", "created_at", "modified_at", "last_activity_at"],
    typer.Option(help="Sort by name, created_at, modified_at, or last_activity_at."),
]

DESCENDING = Annotated[bool, typer.Option(help="Reverse primary sort order.")]

GROUP = Annotated[
    bool,
    typer.Option(
        "--group/--no-group",
        help="Group rows under status headers; use --no-group for a flat list.",
    ),
]

LIMIT = Annotated[
    int | None,
    typer.Option("--limit", min=1, help="Maximum results (positive integer)."),
]
