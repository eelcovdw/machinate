from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import (
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
)
from machinate.cli.options import (
    CLEAR_TAGS,
    DESCENDING,
    GROUP,
    LIMIT,
    MATCH_TAGS,
    OUTPUT_FORMAT,
    PLAN,
    PROJECT_DIR,
    SORT,
    SUMMARY,
    TAGS,
    TASK_STATUS,
    TASK_STATUS_FILTER,
)
from machinate.cli.update_options import UpdateOptions, build_update
from machinate.models.documents import TaskStatus
from machinate.models.operations import BatchCreated, StatusCreateInput, StatusUpdate, TaskQuery


def task_add_command(  # noqa: PLR0913
    ctx: typer.Context,
    names: Annotated[list[str], typer.Argument(help="Name(s) of the task(s) to create.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    tags: TAGS = None,
    summary: SUMMARY = None,
    status: TASK_STATUS = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Create one or more tasks in a plan."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        batch = services.tasks.create_many(
            plan_name,
            names,
            StatusCreateInput[TaskStatus](tags=tags or [], summary=summary, status=status),
        )
        result = TaskAddResult(
            command="task add",
            project=services.project,
            plan_name=plan_name,
            batch=BatchCreated(
                created=[task.record for task in batch.created], failures=batch.failures
            ),
        )
        run.render(result)


def task_list_command(  # noqa: PLR0913
    ctx: typer.Context,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
    tags: MATCH_TAGS = None,
    statuses: TASK_STATUS_FILTER = None,
    sort: SORT = "name",
    descending: DESCENDING = False,
    group: GROUP = True,
    limit: LIMIT = None,
) -> None:
    """List tasks in a plan."""
    with execute(ctx, output_format) as run:
        query = TaskQuery(
            tags=set(tags) if tags is not None else None,
            statuses=set(statuses) if statuses is not None else None,
            sort=sort,
            descending=descending,
            limit=limit,
        )
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        result = TaskListResult(
            command="task list",
            project=services.project,
            plan_name=plan_name,
            tasks=services.tasks.list_records(plan_name, query),
            group_by="status" if group else None,
        )
        run.render(result)


def task_show_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the task to show.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show task metadata and body."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        task = services.tasks.get(plan_name, name)
        result = TaskShowResult(
            command="task show",
            project=services.project,
            plan_name=plan_name,
            task=task.record,
            body=task.body,
        )
        run.render(result)


def task_info_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the task to inspect.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show task metadata."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        task = services.tasks.get_info(plan_name, name)
        result = TaskInfoResult(
            command="task info", project=services.project, plan_name=plan_name, task=task
        )
        run.render(result)


def task_update_command(  # noqa: PLR0913
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the task to update.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    summary: SUMMARY = None,
    status: TASK_STATUS = None,
    tags: TAGS = None,
    clear_tags: CLEAR_TAGS = False,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Change task status, summary, or tags."""
    with execute(ctx, output_format) as run:
        update = build_update(
            StatusUpdate[TaskStatus],
            UpdateOptions(summary=summary, status=status, tags=tags, clear_tags=clear_tags),
            hint="--summary, --status, --tag, or --clear-tags",
        )
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        updated = services.tasks.update(plan_name, name, update)
        result = TaskUpdateResult(
            command="task update",
            project=services.project,
            plan_name=plan_name,
            task=updated.record,
            body=updated.body,
        )
        run.render(result)


def task_path_command(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Task name; omit to print the plan's tasks directory."),
    ] = None,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a task document or the tasks directory."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        located = services.tasks.locate(plan_name, name)
        run.render_path(command="task path", plan_name=plan_name, located=located)
