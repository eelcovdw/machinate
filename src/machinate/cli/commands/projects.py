from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import InfoResult, InitResult
from machinate.cli.options import OUTPUT_FORMAT, PROJECT_DIR


def init_project(
    context: typer.Context,
    project_directory: PROJECT_DIR = None,
    project_name: Annotated[
        str | None, typer.Option("--project-name", help="Project name; defaults to directory name.")
    ] = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Initialize the target directory as a Machinate project."""
    with execute(context, output_format) as run:
        scope = run.dependencies.initialize_project(project_directory, project_name)
        run.render(InitResult(command="init", project=scope))


def info_command(
    context: typer.Context,
    project_directory: PROJECT_DIR = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Show a project overview."""
    with execute(context, output_format) as run:
        project_context = run.prepare(project_directory)
        run.render(
            InfoResult(
                command="info",
                project=project_context.project,
                overview=project_context.overviews.project_overview(),
            )
        )
