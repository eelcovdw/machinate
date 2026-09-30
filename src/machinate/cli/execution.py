"""Shared per-command execution plumbing: settings, formatter, project, error output."""

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

import click
import typer
from pydantic import ValidationError

from machinate.models.documents import LoadedPlan
from machinate.services.document import LocatedPath
from machinate.services.errors import NotFoundError, ServiceError
from machinate.services.plan import PlanService
from machinate.storage.errors import StorageError

from .dependencies import Dependencies, get_dependencies, get_settings
from .errors import EXIT_ERROR, MissingTargetPlanError, describe_error
from .formatting import Formatter, JsonFormatter, UnknownFormatError, get_formatter
from .models import (
    CommandResult,
    ContextAddResult,
    DocAddResult,
    ErrorResult,
    PathResult,
    ProjectScope,
    TaskAddResult,
)
from .project_setup import ProjectError, ProjectServices
from .settings import Settings

REPORTED_ERRORS: tuple[type[Exception], ...] = (
    ServiceError,
    ProjectError,
    UnknownFormatError,
    StorageError,
    ValidationError,
    OSError,
)

type PathCommand = Literal["plan path", "task path", "context path", "doc path"]

_ADD_RESULTS_WITH_BATCH = (TaskAddResult, ContextAddResult, DocAddResult)


def command_label(ctx: click.Context) -> str:
    """Build the space-separated command path from the click context."""
    names: list[str] = []
    current = ctx
    while current.parent is not None:
        if current.info_name:
            names.append(current.info_name)
        current = current.parent
    return " ".join(reversed(names)) or "machi"


def resolve_formatter(
    override: str | None, settings: Settings, dependencies: Dependencies
) -> Formatter:
    """Resolve the effective formatter (--format, then settings, then default)."""
    return get_formatter(override or settings.format, dependencies.formatters)


@dataclass
class Execution:
    """Per-command state: dependencies, resolved settings and formatter, project scope."""

    dependencies: Dependencies
    settings: Settings
    formatter: Formatter
    command: str
    project: ProjectScope | None = None

    def open_project(self, project_directory: Path | None) -> ProjectServices:
        """Load the project, recording its scope for later error output."""
        services = self.dependencies.open_project(project_directory)
        self.project = services.project
        return services

    def fail(self, exc: Exception) -> NoReturn:
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
        if isinstance(result, _ADD_RESULTS_WITH_BATCH) and result.batch.failures:
            raise typer.Exit(EXIT_ERROR)

    def render_path(
        self,
        *,
        command: PathCommand,
        plan_name: str | None,
        located: LocatedPath,
    ) -> None:
        """Render the absolute path, kind, and existence of a document or directory."""
        self.render(
            PathResult(
                command=command,
                project=self.require_project(),
                plan_name=plan_name,
                absolute_path=located.path,
                kind=located.kind,
                # Only directory kinds report existence; document paths are validated.
                exists=located.exists if located.kind.endswith("_directory") else None,
            )
        )

    def require_project(self) -> ProjectScope:
        """Return the prepared project's scope, failing if the command did not prepare one."""
        if self.project is None:
            msg = "Project has not been prepared."
            raise RuntimeError(msg)
        return self.project

    def determine_plan_name(self, plans: PlanService, name: str | None) -> str:
        """Determine the explicit or current plan name, enforcing agent targeting."""
        if name is not None:
            return name
        if self.settings.is_agent_mode:
            msg = "Agent mode requires an explicit plan; use -p NAME."
            raise MissingTargetPlanError(msg)
        current = plans.find_current_plan()
        if current is None:
            msg = "No current plan is selected; use -p NAME."
            raise MissingTargetPlanError(msg)
        try:
            plans.get_path(current)
        except NotFoundError as err:
            msg = f"Current plan {current!r} no longer exists; use -p NAME or plan select."
            raise MissingTargetPlanError(msg) from err
        return current

    def get_target_plan(self, plans: PlanService, name: str | None) -> LoadedPlan:
        """Determine the target plan name and load its document."""
        return plans.get(self.determine_plan_name(plans, name))

    def require_human_session(self) -> None:
        """Reject session-mutating plan selection commands in agent mode."""
        if self.settings.is_agent_mode:
            msg = "Plan selection is unavailable in agent mode."
            raise MissingTargetPlanError(msg)


@contextmanager
def execute(
    ctx: click.Context,
    output_format: str | None,
) -> Generator[Execution]:
    """Resolve settings and formatter, and route failures to structured error output."""
    dependencies = get_dependencies(ctx)
    execution = Execution(
        dependencies=dependencies,
        settings=Settings.model_construct(),  # Replaced below, once settings resolve.
        formatter=JsonFormatter(),  # Structured fallback if settings/format selection fails.
        command=command_label(ctx),
    )
    try:
        execution.settings = get_settings(ctx)
        execution.formatter = resolve_formatter(output_format, execution.settings, dependencies)
    except (ValidationError, UnknownFormatError) as exc:
        execution.fail(exc)
    try:
        yield execution
    except BrokenPipeError:
        _exit_broken_pipe()
    except REPORTED_ERRORS as exc:
        execution.fail(exc)


def _exit_broken_pipe() -> NoReturn:
    """Exit quietly when the reader closes the pipe, as a Unix filter should."""
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    raise typer.Exit(0)
