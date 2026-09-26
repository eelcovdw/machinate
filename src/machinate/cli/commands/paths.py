from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from machinate.cli.commands.selection import PlanSelectionError, select_plan
from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import ErrorResult, PathResult, ProjectScope
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.storage.errors import StorageError
from machinate.storage.models import ContextNameInput, TaskNameInput

_PLAN = Annotated[
    str | None,
    typer.Option("--plan", "-p", help="Plan to target; defaults to the current plan."),
]
_PROJECT = Annotated[
    Path | None,
    typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
]
_OUTPUT_FORMAT = Annotated[
    str | None, typer.Option("--format", help="Formatter name (text or json by default).")
]


def plan_path(
    context: typer.Context,
    plan: _PLAN = None,
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute editing path of a plan document."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        result = PathResult(
            command="plan path",
            project=scope,
            plan=selected.name,
            path=scope.storage / selected.path,
            kind="plan",
            exists=True,
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
            formatter.format(ErrorResult(command="plan path", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def task_path(
    context: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Task name; omit to print the plan's tasks directory."),
    ] = None,
    plan: _PLAN = None,
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a task document or the tasks directory."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        task_name = None if name is None else TaskNameInput(name=name).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        if task_name is None:
            target = scope.storage / project_context.tasks.directory(selected.name)
            result = PathResult(
                command="task path",
                project=scope,
                plan=selected.name,
                path=target,
                kind="tasks_directory",
                exists=target.is_dir(),
            )
        else:
            task = project_context.tasks.get(selected.name, task_name)
            result = PathResult(
                command="task path",
                project=scope,
                plan=selected.name,
                path=scope.storage / task.path,
                kind="task",
                exists=True,
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
            formatter.format(ErrorResult(command="task path", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def context_path(
    context: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Context name; omit to print the plan's context directory."),
    ] = None,
    plan: _PLAN = None,
    project: _PROJECT = None,
    output_format: _OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a context document or the context directory."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        context_name = None if name is None else ContextNameInput(name=name).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        if context_name is None:
            target = scope.storage / project_context.contexts.directory(selected.name)
            result = PathResult(
                command="context path",
                project=scope,
                plan=selected.name,
                path=target,
                kind="context_directory",
                exists=target.is_dir(),
            )
        else:
            document = project_context.contexts.get(selected.name, context_name)
            result = PathResult(
                command="context path",
                project=scope,
                plan=selected.name,
                path=scope.storage / document.path,
                kind="context",
                exists=True,
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
            formatter.format(ErrorResult(command="context path", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
