from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from machinate.cli.commands.selection import PlanSelectionError, select_plan
from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import (
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ErrorResult,
    ProjectScope,
)
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.storage import ContextMetadata
from machinate.storage.errors import StorageError
from machinate.storage.models import ContextNameInput
from machinate.storage.queries import DocumentQuery


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
    """Create one or more context documents in a plan without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        context_names = [ContextNameInput(name=name).name for name in names]
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        created = [
            project_context.contexts.create(
                selected.name, name, ContextMetadata(created=datetime.now(UTC), tags=tags or [])
            )
            for name in context_names
        ]
        result = ContextAddResult(project=scope, plan=selected.name, contexts=created)
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
            formatter.format(ErrorResult(command="context add", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


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
    search: Annotated[
        str | None, typer.Option(help="Substring search in name and summary.")
    ] = None,
    search_body: Annotated[bool, typer.Option(help="Include document body in search.")] = False,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Match any tag. Repeat for multiple tags."),
    ] = None,
    sort: Annotated[str, typer.Option(help="Sort by name, created, or updated.")] = "name",
    descending: Annotated[bool, typer.Option(help="Reverse primary sort order.")] = False,
    limit: Annotated[str | None, typer.Option(help="Maximum results (positive integer).")] = None,
) -> None:
    """List context documents in a plan without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        query = DocumentQuery.model_validate(
            {
                "search": search,
                "search_body": search_body,
                "tags": tags,
                "sort": sort,
                "descending": descending,
                "limit": limit,
            }
        )
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        result = ContextListResult(
            project=scope,
            plan=selected.name,
            contexts=project_context.contexts.list(selected.name, query),
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
            formatter.format(ErrorResult(command="context list", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


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
    """Show a context document without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        context_name = ContextNameInput(name=name).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        document = project_context.contexts.get(selected.name, context_name)
        result = ContextShowResult(project=scope, plan=selected.name, context=document)
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
            formatter.format(ErrorResult(command="context show", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))


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
    """Show a context's metadata (without its body) without changing selection."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    scope: ProjectScope | None = None
    try:
        settings = Settings()
        formatter = select_formatter(output_format or settings.format, dependencies.formatters)
        context_name = ContextNameInput(name=name).name
        project_context = dependencies.prepare_project(project)
        scope = project_context.project
        selected = select_plan(project_context.plans, plan, interactive=settings.interactive)
        document = project_context.contexts.info(selected.name, context_name)
        result = ContextInfoResult(project=scope, plan=selected.name, context=document)
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
            formatter.format(ErrorResult(command="context info", error=message, project=scope)),
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
