from pathlib import Path
from typing import Annotated

import typer

from machinate.cli.errors import PlanSelectionError
from machinate.cli.execution import execute
from machinate.cli.models import (
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ContextUpdateResult,
)
from machinate.cli.update_changes import UpdateOptions, build_update
from machinate.models.operations import ContextUpdate, CreateInput, DocumentQuery


def context_changes(
    summary: str | None,
    tags: list[str] | None,
    clear_tags: bool = False,
) -> ContextUpdate:
    """Validate provided options and build a context update with only the changed fields."""
    return build_update(
        ContextUpdate,
        UpdateOptions(summary=summary, tags=tags, clear_tags=clear_tags),
        hint="--summary, --tag, or --clear-tags",
    )


def context_add(  # noqa: PLR0913
    context: typer.Context,
    names: Annotated[
        list[str], typer.Argument(help="Name(s) of the context document(s) to create.")
    ],
    plan: Annotated[
        str | None,
        typer.Option("--plan", "-p", help="Plan to add contexts to; defaults to the current plan."),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option(
            "--tag", help="Tag(s) to apply to every created context. Repeat for multiple tags."
        ),
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Create one or more context documents in a plan."""
    with execute(context, "context add", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        created, errors = project_context.contexts.create_batch(
            plan_name, names, CreateInput(tags=tags or [])
        )
        result = ContextAddResult(
            project=project_context.project,
            plan=plan_name,
            contexts=[context.record for context in created],
            body="",
            errors=errors,
        )
        run.render(result)
    if result.errors:
        raise typer.Exit(1)  # Partial failure; the result still reports what was created.


def context_list(  # noqa: PLR0913
    context: typer.Context,
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan whose contexts to list; defaults to the current plan."
        ),
    ] = None,
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
    sort: Annotated[str, typer.Option(help="Sort by name, created_at, or modified_at.")] = "name",
    descending: Annotated[bool, typer.Option(help="Reverse primary sort order.")] = False,
    limit: Annotated[str | None, typer.Option(help="Maximum results (positive integer).")] = None,
) -> None:
    """List context documents in a plan."""
    with execute(context, "context list", output_format, PlanSelectionError) as run:
        query = DocumentQuery.model_validate(
            {
                "tags": tags,
                "sort": sort,
                "descending": descending,
                "limit": limit,
            }
        )
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        result = ContextListResult(
            project=project_context.project,
            plan=plan_name,
            contexts=project_context.contexts.list(plan_name, query),
        )
        run.render(result)


def context_show(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context document to show.")],
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan containing the context; defaults to the current plan."
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
    """Show context metadata and body."""
    with execute(context, "context show", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        document = project_context.contexts.get(plan_name, name)
        result = ContextShowResult(
            project=project_context.project,
            plan=plan_name,
            context=document.record,
            body=document.body,
        )
        run.render(result)


def context_info(
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context document to inspect.")],
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan containing the context; defaults to the current plan."
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
    """Show context metadata."""
    with execute(context, "context info", output_format, PlanSelectionError) as run:
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        document = project_context.contexts.info(plan_name, name)
        result = ContextInfoResult(
            project=project_context.project, plan=plan_name, context=document
        )
        run.render(result)


def context_update(  # noqa: PLR0913
    context: typer.Context,
    name: Annotated[str, typer.Argument(help="Name of the context document to update.")],
    plan: Annotated[
        str | None,
        typer.Option(
            "--plan", "-p", help="Plan containing the context; defaults to the current plan."
        ),
    ] = None,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact project directory; otherwise discover upward."),
    ] = None,
    summary: Annotated[
        str | None,
        typer.Option("--summary", help="New summary; pass an empty string to clear it."),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Replace the context's tags. Repeat for multiple tags."),
    ] = None,
    clear_tags: Annotated[
        bool,
        typer.Option("--clear-tags", help="Remove all tags; mutually exclusive with --tag."),
    ] = False,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Change context summary or tags."""
    with execute(context, "context update", output_format, PlanSelectionError) as run:
        changes = context_changes(summary, tags, clear_tags)
        project_context = run.prepare(project)
        plan_name = run.determine_plan_name(project_context.plans, plan)
        updated = project_context.contexts.update(plan_name, name, changes)
        result = ContextUpdateResult(
            project=project_context.project,
            plan=plan_name,
            context=updated.record,
            body=updated.body,
        )
        run.render(result)
