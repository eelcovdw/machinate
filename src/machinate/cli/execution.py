"""Shared per-command execution plumbing: settings, formatter, project, error output."""

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import click
import typer
from pydantic import ValidationError

from machinate.models.documents import LoadedPlan
from machinate.services.errors import NotFoundError, ServiceError
from machinate.services.plan import PlanService
from machinate.storage.errors import StorageError

from .dependencies import Dependencies, get_dependencies, get_settings
from .errors import EXIT_ERROR, PlanSelectionError, describe_error
from .formatting import Formatter, JsonFormatter, UnknownFormatError, select_formatter
from .models import (
    CommandResult,
    ContextAddResult,
    DocAddResult,
    ErrorResult,
    ProjectScope,
    TaskAddResult,
)
from .project_setup import ProjectContext, ProjectError
from .settings import Settings

DEFAULT_ERRORS: tuple[type[Exception], ...] = (
    ServiceError,
    ProjectError,
    UnknownFormatError,
    StorageError,
    ValidationError,
    OSError,
)

_ADD_RESULTS_WITH_BATCH = (TaskAddResult, ContextAddResult, DocAddResult)


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
        """Render an error through the resolved formatter and exit with the error code."""
        detail = describe_error(exc)
        typer.echo(
            self.formatter.format(
                ErrorResult(
                    command=self.command,
                    error=detail.message,
                    code=detail.code,
                    project=self.project,
                )
            ),
            err=True,
        )
        raise typer.Exit(EXIT_ERROR) from exc

    def render(self, result: CommandResult) -> None:
        """Render a command result, failing the batch commands when any name failed."""
        typer.echo(self.formatter.format(result))
        if isinstance(result, _ADD_RESULTS_WITH_BATCH) and result.batch.errors:
            raise typer.Exit(EXIT_ERROR)

    def determine_plan_name(self, plans: PlanService, name: str | None) -> str:
        """Determine the explicit or current plan name, enforcing agent targeting."""
        if name is not None:
            return name
        if self.settings.is_agent_mode:
            msg = "Agent mode requires an explicit plan; use -p NAME."
            raise PlanSelectionError(msg)
        current = plans.current_name()
        if current is None:
            msg = "No current plan is selected; use -p NAME."
            raise PlanSelectionError(msg)
        try:
            plans.path(current)
        except NotFoundError as err:
            msg = f"Current plan {current!r} no longer exists; use -p NAME or plan select."
            raise PlanSelectionError(msg) from err
        return current

    def get_target_plan(self, plans: PlanService, name: str | None) -> LoadedPlan:
        """Determine the target plan name and load its document."""
        return plans.get(self.determine_plan_name(plans, name))

    def require_human_session(self) -> None:
        """Reject session-mutating plan selection commands in agent mode."""
        if self.settings.is_agent_mode:
            msg = "Plan selection is unavailable in agent mode."
            raise PlanSelectionError(msg)


@contextmanager
def execute(
    context: click.Context,
    command: str,
    output_format: str | None,
) -> Generator[Execution]:
    """Resolve settings and formatter, and route failures to structured error output."""
    dependencies = get_dependencies(context)
    execution = Execution(
        dependencies=dependencies,
        settings=Settings.model_construct(),  # Replaced below, once settings resolve.
        formatter=JsonFormatter(),  # Structured fallback if settings/format selection fails.
        command=command,
    )
    try:
        execution.settings = get_settings(context)
        execution.formatter = resolve_formatter(output_format, execution.settings, dependencies)
    except (ValidationError, UnknownFormatError) as exc:
        execution.report(exc)
    try:
        yield execution
    except BrokenPipeError:
        _exit_broken_pipe()
    except DEFAULT_ERRORS as exc:
        execution.report(exc)


def _exit_broken_pipe() -> NoReturn:
    """Exit quietly when the reader closes the pipe, as a Unix filter should."""
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    raise typer.Exit(0)
