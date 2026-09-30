from typing import Annotated

import typer

from machinate.cli.errors import EXIT_ERROR
from machinate.cli.execution import execute
from machinate.cli.models import (
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ContextUpdateResult,
)
from machinate.cli.options import (
    CLEAR_TAGS,
    DESCENDING,
    LIMIT,
    MATCH_TAGS,
    OUTPUT_FORMAT,
    PLAN,
    PROJECT_DIR,
    SORT,
    SUMMARY,
    TAGS,
    build_update,
)
from machinate.models.operations import CreateInput, DocumentQuery, DocumentUpdate


def context_add_command(
    ctx: typer.Context,
    names: Annotated[list[str], typer.Argument(help="Name(s) of the contexts to create.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    tags: TAGS = None,
    summary: SUMMARY = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Create one or more contexts in a plan."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        batch = services.contexts.create_many(
            plan_name, names, CreateInput(tags=tags or [], summary=summary)
        )
        result = ContextAddResult(
            command="context add",
            project=services.project,
            plan_name=plan_name,
            batch=batch,
        )
        run.emit(result)
        if result.batch.failures:
            raise typer.Exit(EXIT_ERROR)


def context_list_command(
    ctx: typer.Context,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
    tags: MATCH_TAGS = None,
    sort: SORT = "name",
    descending: DESCENDING = False,
    limit: LIMIT = None,
) -> None:
    """List contexts in a plan."""
    with execute(ctx, output_format) as run:
        query = DocumentQuery(
            tags=set(tags) if tags is not None else None,
            sort=sort,
            descending=descending,
            limit=limit,
        )
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        result = ContextListResult(
            command="context list",
            project=services.project,
            plan_name=plan_name,
            contexts=services.contexts.list_records(plan_name, query),
        )
        run.emit(result)


def context_show_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context to show.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show context metadata and body."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        document = services.contexts.get(plan_name, name)
        result = ContextShowResult(
            command="context show",
            project=services.project,
            plan_name=plan_name,
            context=document.record,
            body=document.body,
        )
        run.emit(result)


def context_info_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context to inspect.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show context metadata."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        document = services.contexts.get_record(plan_name, name)
        result = ContextInfoResult(
            command="context info",
            project=services.project,
            plan_name=plan_name,
            context=document,
        )
        run.emit(result)


def context_update_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context to update.")],
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    summary: SUMMARY = None,
    tags: TAGS = None,
    clear_tags: CLEAR_TAGS = False,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Change context summary or tags."""
    with execute(ctx, output_format) as run:
        update = build_update(
            DocumentUpdate,
            summary=summary,
            tags=tags,
            clear_tags=clear_tags,
            hint="--summary, --tag, or --clear-tags",
        )
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        updated = services.contexts.update(plan_name, name, update)
        result = ContextUpdateResult(
            command="context update",
            project=services.project,
            plan_name=plan_name,
            context=updated.record,
            body=updated.body,
        )
        run.emit(result)


def context_path_command(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Context name; omit to print the plan's context directory."),
    ] = None,
    plan: PLAN = None,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a context or the context directory."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        plan_name = run.determine_plan_name(services.plans, plan)
        located = services.contexts.locate(plan_name, name)
        run.render_path(command="context path", plan_name=plan_name, located=located)
