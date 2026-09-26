from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast, get_args

import typer
from pydantic import ValidationError

from machinate.cli.commands.selection import PlanSelectionError, explicit_plan_name, select_plan
from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import (
    AddResult,
    ErrorResult,
    InfoResult,
    ListResult,
    PlanInfoResult,
    ProjectScope,
    SetResult,
    ShowResult,
    StatusResult,
)
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.storage import PlanMetadata, PlanStatus
from machinate.storage.errors import StorageError
from machinate.storage.models import NameInput
from machinate.storage.queries import PlanQuery


class InvalidStatusError(Exception):
    """Raised when a status value is not one of the accepted plan statuses."""


def plan_status(value: str) -> PlanStatus:
    """Validate a plan status string."""
    allowed = get_args(PlanStatus.__value__)  # pyright: ignore[reportAny]
    if value not in allowed:
        msg = f"Unknown status {value!r}; expected one of: {', '.join(allowed)}."
        raise InvalidStatusError(msg)
    return cast("PlanStatus", value)


def add_plan(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the plan to create.")],
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Tag(s) to apply. Repeat for multiple tags."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Create a plan without changing the selected plan."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        plan_name = NameInput(name=name).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        plan = project_context.plans.create(
            plan_name, PlanMetadata(created=datetime.now(UTC), tags=tags or [])
        )
        result = AddResult(project=scope, plan=plan)
    except (ProjectError, UnknownFormatError, StorageError, ValidationError, OSError) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan add", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def list_plans(  # noqa: PLR0913
    context: typer.Context,
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
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Match any tag. Repeat for multiple tags."),
    ] = None,
    statuses: Annotated[
        list[str] | None,
        typer.Option(
            "--status",
            help="Match any status: draft, active, done. Repeat for multiple statuses.",
        ),
    ] = None,
    sort: Annotated[str, typer.Option(help="Sort by name, created, or updated.")] = "name",
    descending: Annotated[bool, typer.Option(help="Reverse primary sort order.")] = False,
    limit: Annotated[str | None, typer.Option(help="Maximum results (positive integer).")] = None,
) -> None:
    """List plans across the selected project without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        name = output_format or settings.format
        formatter = select_formatter(name, dependencies.formatters)
        query = PlanQuery.model_validate(
            {
                "search": search,
                "search_body": search_body,
                "tags": tags,
                "statuses": statuses,
                "sort": sort,
                "descending": descending,
                "limit": limit,
            }
        )
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        result = ListResult(project=scope, plans=project_context.plans.list(query))
    except (ProjectError, UnknownFormatError, StorageError, ValidationError, OSError) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan list", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def info_command(
    context: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Show a project overview."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        result = InfoResult(project=scope, overview=project_context.plans.project_overview())
    except (ProjectError, UnknownFormatError, StorageError, ValidationError, OSError) as exc:
        typer.echo(
            formatter.format(ErrorResult(command="info", error=describe_error(exc), project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def plan_info_command(
    context: typer.Context,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan to overview; otherwise the current plan."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Show a plan overview without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        plan_name = None if plan is None else NameInput(name=plan).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan_name, interactive=settings.interactive)
        result = PlanInfoResult(
            project=scope, overview=project_context.plans.plan_overview(selected.name)
        )
    except (
        PlanSelectionError,
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan info", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def set_plan(
    context: typer.Context,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan to select as the current plan."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Select an explicit plan as the project's current plan."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        plan_name = explicit_plan_name(plan)
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        state = project_context.plans.set_current(plan_name)
        result = SetResult(project=scope, state=state)
    except (
        PlanSelectionError,
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan set", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def status_plan(
    context: typer.Context,
    status: Annotated[
        str | None,
        typer.Argument(help="New status: draft, active, or done. Omit to read the status."),
    ] = None,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan to inspect or update; otherwise the current plan."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Read or update a plan's status."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        plan_name = None if plan is None else NameInput(name=plan).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan_name, interactive=settings.interactive)
        if status is None:
            result = StatusResult(project=scope, plan=selected)
        else:
            updated = project_context.plans.set_status(selected.name, plan_status(status))
            result = StatusResult(project=scope, plan=updated)
    except (
        InvalidStatusError,
        PlanSelectionError,
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan status", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def show_plan(
    context: typer.Context,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan to show; otherwise the current plan."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Show a plan without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        plan_name = None if plan is None else NameInput(name=plan).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan_name, interactive=settings.interactive)
        result = ShowResult(project=scope, plan=selected)
    except (
        PlanSelectionError,
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan show", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
