from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import (
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
    MATCH_TAGS,
    OUTPUT_FORMAT,
    PLAN,
    PLAN_SORT,
    PLAN_STATUS,
    PLAN_STATUS_FILTER,
    PROJECT_DIR,
    SUMMARY,
    TAGS,
    build_update,
)
from machinate.models.documents import PlanStatus
from machinate.models.operations import PlanQuery, StatusCreateInput, StatusUpdate


def plan_add_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the plan to create.")],
    project_directory: PROJECT_DIR = None,
    tags: TAGS = None,
    summary: SUMMARY = None,
    status: PLAN_STATUS = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Create a plan."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        create = StatusCreateInput[PlanStatus](summary=summary, tags=tags or [], status=status)
        plan = services.plans.create(name, create)
        run.emit(
            PlanAddResult(
                command="plan add",
                project=services.project,
                plan=plan.record,
            )
        )


def plan_list_command(
    ctx: typer.Context,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
    tags: MATCH_TAGS = None,
    statuses: PLAN_STATUS_FILTER = None,
    sort: PLAN_SORT = "name",
    descending: DESCENDING = False,
    group: GROUP = True,
    limit: LIMIT = None,
) -> None:
    """List plans in the project."""
    with execute(ctx, output_format) as run:
        query = PlanQuery(
            tags=set(tags) if tags is not None else None,
            statuses=set(statuses) if statuses is not None else None,
            sort=sort,
            descending=descending,
            limit=limit,
        )
        services = run.open_project(project_directory)
        run.emit(
            PlanListResult(
                command="plan list",
                project=services.project,
                plans=services.plans.list_records(query),
                current_plan=services.plans.find_current_plan(),
                group_by="status" if group else None,
            )
        )


def plan_info_command(
    ctx: typer.Context,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show plan metadata and task progress."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        run.emit(
            PlanInfoResult(
                command="plan info",
                project=services.project,
                overview=services.overviews.get_plan_overview(plan_name),
            )
        )


def plan_select_command(
    ctx: typer.Context,
    name: Annotated[
        str,
        typer.Argument(help="Name of the plan to select as the current plan."),
    ],
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Set the project's current plan; commands use it when -p is omitted."""
    with execute(ctx, output_format) as run:
        run.require_human_session()
        services = run.open_project(project_directory)
        state = services.plans.select_plan(name)
        run.emit(
            PlanSelectResult(
                command="plan select",
                project=services.project,
                current_plan=state.current_plan,
            )
        )


def plan_unselect_command(
    ctx: typer.Context,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Clear the current plan; does not change any plan's status."""
    with execute(ctx, output_format) as run:
        run.require_human_session()
        services = run.open_project(project_directory)
        state = services.plans.unselect_plan()
        run.emit(
            PlanUnselectResult(
                command="plan unselect",
                project=services.project,
                current_plan=state.current_plan,
            )
        )


def plan_update_command(
    ctx: typer.Context,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    summary: SUMMARY = None,
    status: PLAN_STATUS = None,
    tags: TAGS = None,
    clear_tags: CLEAR_TAGS = False,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Change plan status, summary, or tags."""
    with execute(ctx, output_format) as run:
        update = build_update(
            StatusUpdate[PlanStatus],
            summary=summary,
            status=status,
            tags=tags,
            clear_tags=clear_tags,
            hint="--summary, --status, --tag, or --clear-tags",
        )
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        updated = services.plans.update(plan_name, update)
        run.emit(
            PlanUpdateResult(
                command="plan update",
                project=services.project,
                plan=updated.record,
                body=updated.body,
            )
        )


def plan_path_command(
    ctx: typer.Context,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute editing path of a plan document."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        located = services.plans.locate(plan_name)
        run.render_path(command="plan path", plan_name=plan_name, located=located)


def plan_show_command(
    ctx: typer.Context,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show plan metadata and body."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        selected = services.plans.get(plan_name)
        run.emit(
            PlanShowResult(
                command="plan show",
                project=services.project,
                plan=selected.record,
                body=selected.body,
            )
        )
