"""Shared CLI option definitions.

Every option used by more than one command is declared here once, as an ``Annotated``
alias. Command modules import the alias; only options whose choices genuinely differ per
resource (status) have more than one alias.
"""

from pathlib import Path
from typing import Annotated

import click
import typer
from pydantic import BaseModel

from machinate.models.documents import PLAN_STATUSES, TASK_STATUSES, PlanStatus, TaskStatus
from machinate.models.operations import DOCUMENT_SORTS, PLAN_SORTS, DocumentSort, PlanSort
from machinate.services.errors import InputError

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


def build_update[M: BaseModel](  # noqa: PLR0913 - one keyword per update field
    model: type[M],
    *,
    summary: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    clear_tags: bool = False,
    hint: str,
) -> M:
    """Build a validated update model from the raw CLI options that were supplied.

    Only the provided options become fields, so an omitted field never resets a stored
    value. ``hint`` names the options that would have an effect when none were passed.
    """
    update: dict[str, object] = {}
    if summary is not None:
        update["summary"] = summary
    if status is not None:
        update["status"] = status
    if clear_tags:
        if tags is not None:
            msg = "--tag and --clear-tags are mutually exclusive."
            raise InputError(msg)
        update["tags"] = []
    elif tags is not None:
        update["tags"] = tags
    if not update:
        msg = f"Nothing to update; pass {hint}."
        raise InputError(msg)
    return model.model_validate(update)
