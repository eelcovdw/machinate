from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from machinate.cli.dependencies import get_dependencies
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import ErrorResult, ListResult, ProjectScope
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.storage.errors import StorageError
from machinate.storage.queries import PlanQuery


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
    statuses: Annotated[
        list[str] | None,
        typer.Option(
            "--statuses",
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
        name = settings.formatter_name(output_format)
        formatter = select_formatter(name, dependencies.formatters)
        query = PlanQuery.model_validate(
            {
                "search": search,
                "search_body": search_body,
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
        typer.echo(formatter.format(ErrorResult(error=str(exc), project=scope)), err=True)
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
