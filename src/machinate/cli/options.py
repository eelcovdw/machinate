"""Shared CLI option definitions.

Every option used by more than one command is declared here once, as an ``Annotated``
alias. Command modules import the alias; only options whose choices genuinely differ per
resource (status) have more than one alias.
"""

from pathlib import Path
from typing import Annotated

import click
import typer

from machinate.models.documents import PLAN_STATUSES, TASK_STATUSES, PlanStatus, TaskStatus
from machinate.models.operations import DOCUMENT_SORTS, PLAN_SORTS, DocumentSort, PlanSort

from .formatting import OutputFormat

OUTPUT_FORMAT = Annotated[
    OutputFormat | None,
    typer.Option(
        "--format",
        click_type=click.Choice(["text", "json"]),
        help="Output format: text or json.",
    ),
]

PROJECT_DIR = Annotated[
    Path | None,
    typer.Option("--project-dir", "-P", help="Exact project directory; otherwise discover upward."),
]

PLAN = Annotated[
    str | None,
    typer.Option("--plan", "-p", help="Plan to use; otherwise the current plan."),
]

SEARCH_PLAN = Annotated[
    str | None,
    typer.Option(
        "--plan", "-p", help="Narrow the search to one plan; otherwise search everything."
    ),
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
    PlanStatus | None,
    typer.Option(
        "--status",
        help=f"Status: {', '.join(PLAN_STATUSES)}.",
        click_type=click.Choice(PLAN_STATUSES),
    ),
]

TASK_STATUS = Annotated[
    TaskStatus | None,
    typer.Option(
        "--status",
        help=f"Status: {', '.join(TASK_STATUSES)}.",
        click_type=click.Choice(TASK_STATUSES),
    ),
]

PLAN_STATUS_FILTER = Annotated[
    list[PlanStatus] | None,
    typer.Option(
        "--status",
        help="Match any status. Repeat for multiple statuses.",
        click_type=click.Choice(PLAN_STATUSES),
    ),
]

TASK_STATUS_FILTER = Annotated[
    list[TaskStatus] | None,
    typer.Option(
        "--status",
        help="Match any status. Repeat for multiple statuses.",
        click_type=click.Choice(TASK_STATUSES),
    ),
]

SORT = Annotated[
    DocumentSort,
    typer.Option(
        click_type=click.Choice(DOCUMENT_SORTS), help="Sort by name, created_at, or modified_at."
    ),
]

PLAN_SORT = Annotated[
    PlanSort,
    typer.Option(
        click_type=click.Choice(PLAN_SORTS),
        help="Sort by name, created_at, modified_at, or last_activity_at.",
    ),
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
