from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from machinate.cli.errors import PlanSelectionError
from machinate.cli.execution import execute
from machinate.cli.models import (
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
)
from machinate.cli.update_changes import UpdateOptions, build_update
from machinate.models.task import TaskUpdate
from machinate.storage import TaskMetadata
from machinate.storage.queries import TaskQuery


def task_changes(
    summary: str | None,
    status: str | None,
    tags: list[str] | None,
    clear_tags: bool = False,
) -> TaskUpdate:
    """Validate provided options and build a task update with only the changed fields."""
    return build_update(
        TaskUpdate,
        UpdateOptions(summary=summary, status=status, tags=tags, clear_tags=clear_tags),
        hint="--summary, --status, --tag, or --clear-tags",
    )


def task_add(  # noqa: PLR0913
    context: typer.Context,
    names: Annotated[list[str], typer.Argument(help="Name(s) of the task(s) to create.")],
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan to add tasks to; defaults to the current plan."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tag", help="Tag(s) to apply to every created task. Repeat for multiple tags."
        ),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Create one or more tasks in a plan."""
    with execute(context, "task add", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        created, errors = project_context.tasks.create_batch(
            plan_name, names, TaskMetadata(created=datetime.now(UTC), tags=tags or [])
        )
        result = TaskAddResult(
            project=project_context.project, plan=plan_name, tasks=created, errors=errors
        )
        run.render(result)
    if result.errors:
        raise typer.Exit(1)  # Partial failure; the result still reports what was created.


def task_list(  # noqa: PLR0913
    context: typer.Context,
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan whose tasks to list; defaults to the current plan."
        ),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Match any tag. Repeat for multiple tags."),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        typer.Option(
            "--status",
            help="Match any status: todo, in-progress, done. Repeat for multiple statuses.",
        ),
    ] = None,
    sort: Annotated[str, typer.Option(help="Sort by name, created, or updated.")] = "name",
    descending: Annotated[bool, typer.Option(help="Reverse primary sort order.")] = False,
    group: Annotated[
        bool,
        typer.Option(
            "--group/--no-group",
            help="Group rows under status headers; use --no-group for a flat list.",
        ),
    ] = True,
    limit: Annotated[str | None, typer.Option(help="Maximum results (positive integer).")] = None,
) -> None:
    """List tasks in a plan."""
    with execute(context, "task list", output_format, PlanSelectionError) as run:
        query = TaskQuery.model_validate(
            {
                "tags": tags,
                "statuses": statuses,
                "sort": sort,
                "descending": descending,
                "limit": limit,
            }
        )
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        result = TaskListResult(
            project=project_context.project,
            plan=plan_name,
            tasks=project_context.tasks.list(plan_name, query),
            group_by="status" if group else None,
        )
        run.render(result)


def task_show(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the task to show.")],
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan containing the task; defaults to the current plan."
        ),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Show task metadata and body."""
    with execute(context, "task show", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        task = project_context.tasks.get(plan_name, name)
        result = TaskShowResult(project=project_context.project, plan=plan_name, task=task)
        run.render(result)


def task_info(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the task to inspect.")],
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan containing the task; defaults to the current plan."
        ),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Show task metadata."""
    with execute(context, "task info", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        task = project_context.tasks.info(plan_name, name)
        result = TaskInfoResult(project=project_context.project, plan=plan_name, task=task)
        run.render(result)


def update_task(  # noqa: PLR0913
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the task to update.")],
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan containing the task; defaults to the current plan."
        ),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    summary: Annotated[
        str | None,
        typer.Option("--summary", help="New summary; pass an empty string to clear it."),
    ] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="New status: todo, in-progress, or done.")
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Replace the task's tags. Repeat for multiple tags."),
    ] = None,
    clear_tags: Annotated[
        bool,
        typer.Option("--clear-tags", help="Remove all tags; mutually exclusive with --tag."),
    ] = False,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Change task status, summary, or tags."""
    with execute(
        context,
        "task update",
        output_format,
        PlanSelectionError,
    ) as run:
        changes = task_changes(summary, status, tags, clear_tags)
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        updated = project_context.tasks.update(plan_name, name, changes)
        result = TaskUpdateResult(project=project_context.project, plan=plan_name, task=updated)
        run.render(result)
