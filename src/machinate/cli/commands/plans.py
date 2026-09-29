from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from machinate.cli.errors import PlanSelectionError
from machinate.cli.execution import execute
from machinate.cli.models import (
    AddResult,
    InfoResult,
    ListResult,
    PlanInfoResult,
    SelectResult,
    ShowResult,
    UnselectResult,
    UpdateResult,
)
from machinate.cli.update_changes import UpdateOptions, build_update
from machinate.models.plan import PlanUpdate
from machinate.storage import PlanMetadata
from machinate.storage.queries import PlanQuery


def plan_changes(
    summary: str | None,
    status: str | None,
    tags: list[str] | None,
    clear_tags: bool = False,
) -> PlanUpdate:
    """Validate provided options and build a plan update with only the changed fields."""
    return build_update(
        PlanUpdate,
        UpdateOptions(summary=summary, status=status, tags=tags, clear_tags=clear_tags),
        hint="--summary, --status, --tag, or --clear-tags",
    )


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
    with execute(context, "plan add", output_format) as run:
        project_context = run.prepare(project)
        metadata = PlanMetadata.model_validate(
            {
                "created": datetime.now(UTC),
                "tags": tags or [],
                "summary": summary,
                "status": "draft" if status is None else status,
            }
        )
        plan = project_context.plans.create(name, metadata)
        run.render(AddResult(project=project_context.project, plan=plan))


def list_plans(  # noqa: PLR0913
    context: typer.Context,
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
            help="Match any status: draft, active, done. Repeat for multiple statuses.",
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
    """List plans in the project."""
    with execute(context, "plan list", output_format) as run:
        query = PlanQuery.model_validate(
            {
                "tags": tags,
                "statuses": statuses,
                "sort": sort,
                "descending": descending,
                "limit": limit,
            }
        )
        project_context = run.prepare(project)
        run.render(
            ListResult(
                project=project_context.project,
                plans=project_context.plans.list(query),
                current_plan=project_context.plans.current_name(),
                group_by="status" if group else None,
            )
        )


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
    with execute(context, "info", output_format) as run:
        project_context = run.prepare(project)
        run.render(
            InfoResult(
                project=project_context.project,
                overview=project_context.plans.project_overview(),
            )
        )


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
    with execute(context, "plan info", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        run.render(
            PlanInfoResult(
                project=project_context.project,
                overview=project_context.plans.plan_overview(plan_name),
            )
        )


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
    with execute(context, "plan select", output_format, PlanSelectionError) as run:
        run.require_human_session()
        project_context = run.prepare(project)
        state = project_context.plans.set_current(name)
        run.render(SelectResult(project=project_context.project, state=state))


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
    with execute(context, "plan unselect", output_format, PlanSelectionError) as run:
        run.require_human_session()
        project_context = run.prepare(project)
        state = project_context.plans.clear_current()
        run.render(UnselectResult(project=project_context.project, state=state))


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
    with execute(
        context,
        "plan update",
        output_format,
        PlanSelectionError,
    ) as run:
        changes = plan_changes(summary, status, tags, clear_tags)
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        updated = project_context.plans.update(plan_name, changes)
        run.render(UpdateResult(project=project_context.project, plan=updated))


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
    with execute(context, "plan show", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        selected = run.get_target_plan(project_context.plans, plan)
        run.render(ShowResult(project=project_context.project, plan=selected))
