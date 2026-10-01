from pathlib import Path
from typing import Annotated

import typer

from machinate.cli.execution import execute
from machinate.cli.models import InfoResult, InitResult
from machinate.cli.options import OUTPUT_FORMAT, PROJECT_DIR
from machinate.cli.project_setup import initialize_project, initialize_redirect
from machinate.services.errors import InputError


def init_command(
    ctx: typer.Context,
    project_directory: PROJECT_DIR = None,
    project_name: Annotated[
        str | None, typer.Option("--project-name", help="Project name; defaults to directory name.")
    ] = None,
    redirect: Annotated[
        Path | None,
        typer.Option(
            "--redirect",
            help=(
                "Point this directory at an existing project (shared store) "
                "instead of creating one."
            ),
        ),
    ] = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Initialize the target directory as a Machinate project."""
    with execute(ctx, output_format) as run:
        if redirect is not None:
            if project_name is not None:
                msg = "--redirect and --project-name cannot be combined."
                raise InputError(msg, hint="Drop --project-name; the shared name is used.")
            initialized = initialize_redirect(project_directory, redirect)
            run.emit(
                InitResult(
                    command="init",
                    project=initialized.project,
                    redirected_from=initialized.redirected_from,
                )
            )
            return
        scope = initialize_project(project_directory, project_name)
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
