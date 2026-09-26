from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from machinate.cli.dependencies import get_dependencies
from machinate.cli.errors import describe_error
from machinate.cli.formatting import Formatter, UnknownFormatError, select_formatter
from machinate.cli.models import ErrorResult, InitResult
from machinate.cli.project_setup import ProjectError
from machinate.cli.settings import Settings
from machinate.storage.errors import StorageError


def init_project(
    context: typer.Context,
    project: Annotated[
        Path | None,
        typer.Option("--project", "-P", help="Exact directory to initialize; defaults to current."),
    ] = None,
    project_name: Annotated[
        str | None, typer.Option("--project-name", help="Project name; defaults to directory name.")
    ] = None,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Formatter name (text or json by default).")
    ] = None,
) -> None:
    """Initialize the target directory as a Machinate project."""
    dependencies = get_dependencies(context)
    formatter = Formatter()  # Structured fallback if settings/format selection fails.
    try:
        settings = Settings()
        name = output_format or settings.format
        formatter = select_formatter(name, dependencies.formatters)
        scope = dependencies.initialize_project(project, project_name)
        result = InitResult(project=scope)
    except (ProjectError, UnknownFormatError, StorageError, ValidationError, OSError) as exc:
        typer.echo(
            formatter.format(ErrorResult(command="init", error=describe_error(exc))), err=True
        )
        raise typer.Exit(1) from exc
    typer.echo(formatter.format(result))
