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
    AddResult,
    ErrorResult,
    InfoResult,
    ListResult,
    PlanInfoResult,
    ProjectScope,
    SelectResult,
    ShowResult,
    UnselectResult,
    UpdateResult,
)
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.models.plan import PlanUpdate
from machinate.storage import PlanMetadata, PlanStatus
from machinate.storage.errors import StorageError
from machinate.storage.models import NameInput
from machinate.storage.queries import PlanQuery


class InvalidStatusError(Exception):
    """Raised when a status value is not one of the accepted plan statuses."""


class PlanUpdateError(Exception):
    """Raised when an update is requested with no fields to change."""


def plan_status(value: str) -> PlanStatus:
    """Validate a plan status string."""
    allowed = get_args(PlanStatus.__value__)  # pyright: ignore[reportAny]
    if value not in allowed:
        msg = f"Unknown status {value!r}; expected one of: {', '.join(allowed)}."
        raise InvalidStatusError(msg)
    return cast("PlanStatus", value)


def plan_changes(
    summary: str | None,
    status: str | None,
    tags: list[str] | None,
    clear_tags: bool = False,
) -> PlanUpdate:
    """Validate provided options and build a plan update with only the changed fields."""
    changes: dict[str, object] = {}
    if summary is not None:
        changes["summary"] = summary
    if status is not None:
        changes["status"] = plan_status(status)
    if clear_tags:
        if tags is not None:
            msg = "--tag and --clear-tags are mutually exclusive."
            raise PlanUpdateError(msg)
        changes["tags"] = []
    elif tags is not None:
        changes["tags"] = tags
    if not changes:
        msg = "Nothing to update; pass --summary, --status, --tag, or --clear-tags."
        raise PlanUpdateError(msg)
    return PlanUpdate.model_validate(changes)


def add_plan(  # noqa: PLR0913
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
    summary: Annotated[str | None, typer.Option("--summary", help="Initial summary text.")] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="Initial status: draft, active, or done.")
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Create a plan."""
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
            plan_name,
            PlanMetadata(
                created=datetime.now(UTC),
                tags=tags or [],
                summary=summary,
                status="draft" if status is None else plan_status(status),
            ),
        )
        result = AddResult(project=scope, plan=plan)
    except (
        InvalidStatusError,
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
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
    group_by: Annotated[
        bool,
        typer.Option(
            "--group-by/--no-group-by",
            help="Group rows under status headers; use --no-group-by for a flat list.",
        ),
    ] = True,
    limit: Annotated[str | None, typer.Option(help="Maximum results (positive integer).")] = None,
) -> None:
    """List plans in the project."""
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
        result = ListResult(
            project=scope,
            plans=project_context.plans.list(query),
            group_by="status" if group_by else None,
        )
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
    """Show plan metadata and task progress."""
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
        selected = select_plan(project_context.plans, plan_name, automation=settings.automation)
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


def select_current_plan(
    context: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Name of the plan to select as the current plan."),
    ],
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Set the project's current plan; commands use it when -p is omitted."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        plan_name = NameInput(name=name).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        state = project_context.plans.set_current(plan_name)
        result = SelectResult(project=scope, state=state)
    except (
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan select", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def unselect_plan(
    context: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Clear the current plan; does not change any plan's status."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        state = project_context.plans.clear_current()
        result = UnselectResult(project=scope, state=state)
    except (
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan unselect", error=describe_error(exc), project=scope)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


def update_plan(  # noqa: PLR0913
    context: typer.Context,
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan to update; otherwise the current plan."),
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
        str | None, typer.Option("--status", help="New status: draft, active, or done.")
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Replace the plan's tags. Repeat for multiple tags."),
    ] = None,
    clear_tags: Annotated[
        bool,
        typer.Option("--clear-tags", help="Remove all tags; mutually exclusive with --tag."),
    ] = False,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Change plan status, summary, or tags."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        format_name = output_format or settings.format
        formatter = select_formatter(format_name, dependencies.formatters)
        changes = plan_changes(summary, status, tags, clear_tags)
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, automation=settings.automation)
        updated = project_context.plans.update(selected.name, changes)
        result = UpdateResult(project=scope, plan=updated)
    except (
        InvalidStatusError,
        PlanUpdateError,
        PlanSelectionError,
        ProjectError,
        UnknownFormatError,
        StorageError,
        ValidationError,
        OSError,
    ) as exc:
        typer.echo(
            formatter.format(
                ErrorResult(command="plan update", error=describe_error(exc), project=scope)
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
    """Show plan metadata and body."""
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
        selected = select_plan(project_context.plans, plan_name, automation=settings.automation)
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
