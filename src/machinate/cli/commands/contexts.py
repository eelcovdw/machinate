from typing import Annotated

import typer

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
    PROJECT,
    SORT,
    SUMMARY,
    TAGS,
)
from machinate.cli.update_changes import UpdateOptions, build_update
from machinate.models.operations import BatchCreated, CreateInput, DocumentQuery, DocumentUpdate


def context_add(  # noqa: PLR0913
    context: typer.Context,
    names: Annotated[
        list[str], typer.Argument(help="Name(s) of the context document(s) to create.")
    ],
    plan: PLAN = None,
    project: PROJECT = None,
    tags: TAGS = None,
    summary: SUMMARY = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Create one or more context documents in a plan."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        batch = project_context.contexts.create_batch(
            plan_name, names, CreateInput(tags=tags or [], summary=summary)
        )
        result = ContextAddResult(
            command="context add",
            project=project_context.project,
            plan=plan_name,
            batch=BatchCreated(
                created=[context.record for context in batch.created], errors=batch.errors
            ),
        )
        run.render(result)


def context_list(  # noqa: PLR0913
    context: typer.Context,
    plan: PLAN = None,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
    tags: MATCH_TAGS = None,
    sort: SORT = "name",
    descending: DESCENDING = False,
    limit: LIMIT = None,
) -> None:
    """List context documents in a plan."""
    with execute(context, output_format) as run:
        query = DocumentQuery(
            tags=set(tags) if tags is not None else None,
            sort=sort,
            descending=descending,
            limit=limit,
        )
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        result = ContextListResult(
            command="context list",
            project=project_context.project,
            plan=plan_name,
            contexts=project_context.contexts.list_records(plan_name, query),
        )
        run.render(result)


def context_show(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context document to show.")],
    plan: PLAN = None,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show context metadata and body."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        document = project_context.contexts.get(plan_name, name)
        result = ContextShowResult(
            command="context show",
            project=project_context.project,
            plan=plan_name,
            context=document.record,
            body=document.body,
        )
        run.render(result)


def context_info(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context document to inspect.")],
    plan: PLAN = None,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show context metadata."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        document = project_context.contexts.info(plan_name, name)
        result = ContextInfoResult(
            command="context info",
            project=project_context.project,
            plan=plan_name,
            context=document,
        )
        run.render(result)


def context_update(  # noqa: PLR0913
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context document to update.")],
    plan: PLAN = None,
    project: PROJECT = None,
    summary: SUMMARY = None,
    tags: TAGS = None,
    clear_tags: CLEAR_TAGS = False,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Change context summary or tags."""
    with execute(context, output_format) as run:
        changes = build_update(
            DocumentUpdate,
            UpdateOptions(summary=summary, tags=tags, clear_tags=clear_tags),
            hint="--summary, --tag, or --clear-tags",
        )
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        updated = project_context.contexts.update(plan_name, name, changes)
        result = ContextUpdateResult(
            command="context update",
            project=project_context.project,
            plan=plan_name,
            context=updated.record,
            body=updated.body,
        )
        run.render(result)


def context_path(
    context: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="Context name; omit to print the plan's context directory."),
    ] = None,
    plan: PLAN = None,
    project: PROJECT = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print the absolute path of a context document or the context directory."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        located = project_context.contexts.locate(plan_name, name)
        run.render_path(command="context path", plan=plan_name, located=located)
