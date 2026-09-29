from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import (
    InfoResult,
    PlanAddResult,
    PlanInfoResult,
    PlanListResult,
    PlanSelectResult,
    PlanShowResult,
    PlanUnselectResult,
    PlanUpdateResult,
)
from machinate.cli.options import (
    CLEAR_TAGS,
    DESCENDING,
    GROUP,
    LIMIT,
    OUTPUT_FORMAT,
    PLAN,
    PLAN_SORT,
    PLAN_STATUS,
    PLAN_STATUS_FILTER,
    PROJECT,
    SUMMARY,
    TAGS,
)
from machinate.cli.update_changes import UpdateOptions, build_update
from machinate.models.documents import PlanStatus
from machinate.models.operations import PlanQuery, StatusCreateInput, StatusUpdate


def plan_changes(
    summary: str | None,
    status: str | None,
    tags: list[str] | None,
    clear_tags: bool = False,
) -> StatusUpdate[PlanStatus]:
    """Validate provided options and build a plan update with only the changed fields."""
    return build_update(
        StatusUpdate[PlanStatus],
        UpdateOptions(summary=summary, status=status, tags=tags, clear_tags=clear_tags),
        hint="--summary, --status, --tag, or --clear-tags",
    )


def add_plan(  # noqa: PLR0913
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the plan to create.")],
    project: PROJECT = None,
    tags: TAGS = None,
    summary: SUMMARY = None,
    status: PLAN_STATUS = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Create a plan."""
    with execute(context, "plan add", output_format) as run:
        project_context = run.prepare(project)
        create = StatusCreateInput[PlanStatus].model_validate(
            {"summary": summary, "tags": tags or [], "status": status}
        )
        plan = project_context.plans.create(name, create)
        run.render(
            PlanAddResult(
                command="plan add",
                project=project_context.project,
                plan=plan.record,
            )
        )


def list_plans(  # noqa: PLR0913
    context: typer.Context,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
    tags: TAGS = None,
    statuses: PLAN_STATUS_FILTER = None,
    sort: PLAN_SORT = "name",
    descending: DESCENDING = False,
    group: GROUP = True,
    limit: LIMIT = None,
) -> None:
    """List plans in the project."""
    with execute(context, "plan list", output_format) as run:
        query = PlanQuery(
            tags=set(tags) if tags is not None else None,
            statuses=set(statuses) if statuses is not None else None,
            sort=sort,
            descending=descending,
            limit=limit,
        )
        project_context = run.prepare(project)
        run.render(
            PlanListResult(
                command="plan list",
                project=project_context.project,
                plans=project_context.plans.list_records(query),
                current_plan=project_context.plans.current_name(),
                group_by="status" if group else None,
            )
        )


def info_command(
    context: typer.Context,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show a project overview."""
    with execute(context, "info", output_format) as run:
        project_context = run.prepare(project)
        run.render(
            InfoResult(
                command="info",
                project=project_context.project,
                overview=project_context.overviews.project_overview(),
            )
        )


def plan_info_command(
    context: typer.Context,
    plan: PLAN = None,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show plan metadata and task progress."""
    with execute(context, "plan info", output_format) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        run.render(
            PlanInfoResult(
                command="plan info",
                project=project_context.project,
                overview=project_context.overviews.plan_overview(plan_name),
            )
        )


def select_current_plan(
    context: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Name of the plan to select as the current plan."),
    ],
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Set the project's current plan; commands use it when -p is omitted."""
    with execute(context, "plan select", output_format) as run:
        run.require_human_session()
        project_context = run.prepare(project)
        state = project_context.plans.set_current(name)
        run.render(
            PlanSelectResult(
                command="plan select",
                project=project_context.project,
                current_plan=state.current_plan,
            )
        )


def unselect_plan(
    context: typer.Context,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Clear the current plan; does not change any plan's status."""
    with execute(context, "plan unselect", output_format) as run:
        run.require_human_session()
        project_context = run.prepare(project)
        state = project_context.plans.clear_current()
        run.render(
            PlanUnselectResult(
                command="plan unselect",
                project=project_context.project,
                current_plan=state.current_plan,
            )
        )


def update_plan(  # noqa: PLR0913
    context: typer.Context,
    plan: PLAN = None,
    project: PROJECT = None,
    summary: SUMMARY = None,
    status: PLAN_STATUS = None,
    tags: TAGS = None,
    clear_tags: CLEAR_TAGS = False,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Change plan status, summary, or tags."""
    with execute(
        context,
        "plan update",
        output_format,
    ) as run:
        changes = plan_changes(summary, status, tags, clear_tags)
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        updated = project_context.plans.update(plan_name, changes)
        run.render(
            PlanUpdateResult(
                command="plan update",
                project=project_context.project,
                plan=updated.record,
                body=updated.body,
            )
        )


def show_plan(
    context: typer.Context,
    plan: PLAN = None,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show plan metadata and body."""
    with execute(context, "plan show", output_format) as run:
        project_context = run.prepare(project)
        selected = run.get_target_plan(project_context.plans, plan)
        run.render(
            PlanShowResult(
                command="plan show",
                project=project_context.project,
                plan=selected.record,
                body=selected.body,
            )
        )
