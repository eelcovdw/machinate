"""Shared per-command execution plumbing: settings, formatter, project, error output."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import click
import typer
from pydantic import ValidationError

from machinate.storage.errors import StorageError

from .dependencies import Dependencies, get_dependencies, get_settings
from .errors import InputError, describe_error
from .formatting import Formatter, UnknownFormatError, select_formatter
from .models import CommandResult, ErrorResult, ProjectScope
from .project_setup import ProjectContext, ProjectError
from .settings import Settings

DEFAULT_ERRORS: tuple[type[Exception], ...] = (
    InputError,
    ProjectError,
    UnknownFormatError,
    StorageError,
    ValidationError,
    OSError,
)


def resolve_formatter(
    override: str | None, settings: Settings, dependencies: Dependencies
) -> Formatter:
    """Resolve the effective formatter (--format, then settings, then default)."""
    return select_formatter(override or settings.format, dependencies.formatters)


@dataclass
class Execution:
    """Per-command state: dependencies, resolved settings and formatter, project scope."""

    dependencies: Dependencies
    settings: Settings
    formatter: Formatter
    command: str
    project: ProjectScope | None = None

    def prepare(self, directory: Path | None) -> ProjectContext:
        """Load the project, recording its scope for later error output."""
        project_context = self.dependencies.prepare_project(directory)
        self.project = project_context.project
        return project_context

    def report(self, exc: Exception) -> NoReturn:
        """Render an error through the resolved formatter and exit with status 1."""
        typer.echo(
            self.formatter.format(
                ErrorResult(command=self.command, error=describe_error(exc), project=self.project)
            ),
            err=True,
        )
        raise typer.Exit(1) from exc

    def render(self, result: CommandResult) -> None:
        """Render a command result through the resolved formatter."""
        typer.echo(self.formatter.format(result))


@contextmanager
def execute(
    context: click.Context,
    command: str,
    output_format: str | None,
    *extra_errors: type[Exception],
) -> Generator[Execution]:
    """Resolve settings and formatter, and route failures to structured error output.

    ``command`` labels errors; ``extra_errors`` adds command-specific exceptions to the
    default set already reported here.
    """
    dependencies = get_dependencies(context)
    execution = Execution(
        dependencies=dependencies,
        settings=Settings.model_construct(),  # Replaced below, once settings resolve.
        formatter=Formatter(),  # Structured fallback if settings/format selection fails.
        command=command,
    )
    try:
        execution.settings = get_settings(context)
        execution.formatter = resolve_formatter(output_format, execution.settings, dependencies)
    except (ValidationError, UnknownFormatError) as exc:
        execution.report(exc)
    try:
        yield execution
    except DEFAULT_ERRORS + extra_errors as exc:
        execution.report(exc)
