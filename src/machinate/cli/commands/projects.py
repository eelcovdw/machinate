from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import InfoResult, InitResult
from machinate.cli.options import OUTPUT_FORMAT, PROJECT_DIR


def init_command(
    ctx: typer.Context,
    project_directory: PROJECT_DIR = None,
    project_name: Annotated[
        str | None, typer.Option("--project-name", help="Project name; defaults to directory name.")
    ] = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Initialize the target directory as a Machinate project."""
    with execute(ctx, output_format) as run:
        scope = run.dependencies.initialize_project(project_directory, project_name)
        run.emit(InitResult(command="init", project=scope))


def info_command(
    ctx: typer.Context,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show a project overview."""
    with execute(ctx, output_format) as run:
        services = run.open_project(project_directory)
        run.emit(
            InfoResult(
                command="info",
                project=services.project,
                overview=services.overviews.get_project_overview(),
            )
        )
