from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast, get_args

import typer
from pydantic import ValidationError

from machinate.cli.commands.selection import PlanSelectionError, select_plan
from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import (
    ErrorResult,
    ProjectScope,
    TaskAddResult,
    TaskListResult,
    TaskShowResult,
    TaskStatusResult,
)
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.storage import TaskMetadata
from machinate.storage.errors import StorageError
from machinate.storage.models import NameInput, TaskNameInput, TaskStatus
from machinate.storage.queries import TaskQuery


class InvalidTaskStatusError(Exception):
    """Raised when a status value is not one of the accepted task statuses."""


def task_status(value: str) -> TaskStatus:
    """Validate a task status string."""
    allowed = get_args(TaskStatus.__value__)  # pyright: ignore[reportAny]
    if value not in allowed:
        msg = f"Unknown status {value!r}; expected one of: {', '.join(allowed)}."
        raise InvalidTaskStatusError(msg)
    return cast("TaskStatus", value)


def task_add(
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
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Create one or more tasks in a plan without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        task_names = [TaskNameInput(name=name).name for name in names]
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        created = [
            project_context.tasks.create(
                selected.name, name, TaskMetadata(created=datetime.now(UTC))
            )
            for name in task_names
        ]
        result = TaskAddResult(project=scope, plan=selected.name, tasks=created)
    except (
        ProjectError,
        UnknownFormatError,
        PlanSelectionError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        message = describe_error(exc)
        typer.echo(
            formatter.format(ErrorResult(command="task add", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


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
    search: Annotated[
        str | None, typer.Option(help="Substring search in name and summary.")
    ] = None,
    search_body: Annotated[bool, typer.Option(help="Include document body in search.")] = False,
    statuses: Annotated[
        list[str] | None,
        typer.Option(
            "--status",
            help="Match any status: todo, in-progress, done. Repeat for multiple statuses.",
        ),
    ] = None,
    sort: Annotated[str, typer.Option(help="Sort by name, created, or updated.")] = "name",
    descending: Annotated[bool, typer.Option(help="Reverse primary sort order.")] = False,
    limit: Annotated[str | None, typer.Option(help="Maximum results (positive integer).")] = None,
) -> None:
    """List tasks in a plan without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        query = TaskQuery.model_validate(
            {
                "search": search,
                "search_body": search_body,
                "statuses": statuses,
                "sort": sort,
                "descending": descending,
                "limit": limit,
            }
        )
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        result = TaskListResult(
            project=scope,
            plan=selected.name,
            tasks=project_context.tasks.list(selected.name, query),
        )
    except (
        ProjectError,
        UnknownFormatError,
        PlanSelectionError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        message = describe_error(exc)
        typer.echo(
            formatter.format(ErrorResult(command="task list", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


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
    """Show a task without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        task_name = TaskNameInput(name=name).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        task = project_context.tasks.get(selected.name, task_name)
        result = TaskShowResult(project=scope, plan=selected.name, task=task)
    except (
        ProjectError,
        UnknownFormatError,
        PlanSelectionError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        message = describe_error(exc)
        typer.echo(
            formatter.format(ErrorResult(command="task show", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def status_task(  # noqa: PLR0913
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the task to inspect or update.")],
    status: Annotated[
        str | None,
        typer.Argument(help="New status: todo, in-progress, or done. Omit to read the status."),
    ] = None,
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
    """Read or update a task's status."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        task_name = TaskNameInput(name=name).name
        plan_name = None if plan is None else NameInput(name=plan).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan_name, interactive=settings.interactive)
        task = (
            project_context.tasks.get(selected.name, task_name)
            if status is None
            else project_context.tasks.set_status(selected.name, task_name, task_status(status))
        )
        result = TaskStatusResult(project=scope, plan=selected.name, task=task)
    except (
        InvalidTaskStatusError,
        ProjectError,
        UnknownFormatError,
        PlanSelectionError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        message = describe_error(exc)
        typer.echo(
            formatter.format(ErrorResult(command="task status", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
