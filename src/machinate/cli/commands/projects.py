from pathlib import Path
from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import InitResult


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
    with execute(context, "init", output_format) as run:
        scope = run.dependencies.initialize_project(project, project_name)
        run.render(InitResult(project=scope))
