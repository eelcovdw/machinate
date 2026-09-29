"""Reusable test harness pieces: document seeding and structured CLI invocation.

These live outside ``conftest.py`` so test modules import them by name instead of
importing pytest's special ``conftest`` module. Only fixtures that need ``tmp_path``
or per-test patching stay in ``tests/conftest.py``.
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from click.testing import Result
from pydantic import BaseModel
from typer.testing import CliRunner

from machinate.cli.cli import create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult
from machinate.cli.project_setup import prepare_project
from machinate.cli.settings import LogLevel, Settings
from machinate.models.context import Context
from machinate.models.doc import Doc
from machinate.models.plan import Plan
from machinate.models.task import Task
from machinate.storage import (
    ContextMetadata,
    DocMetadata,
    PlanMetadata,
    PlanStatus,
    ProjectState,
    TaskMetadata,
    TaskStatus,
)

runner = CliRunner()
ModelT = TypeVar("ModelT", bound=BaseModel)

_DEFAULT_CREATED = datetime(2026, 1, 1, tzinfo=UTC)


def filtered_environment() -> dict[str, str]:
    """Return a copy of the environment without Machinate or agent variables."""
    return {
        key: value
        for key, value in os.environ.items()
        if key != "AI_AGENT" and not key.startswith("MACHI_")
    }


process_environment = filtered_environment


def make_settings(
    *,
    automation: bool = False,
    format_name: str | None = None,
    log_level: LogLevel | None = None,
) -> Settings:
    """Build settings with every field explicit, so the environment cannot leak in."""
    return Settings(
        automation=automation,
        format=format_name if format_name is not None else ("json" if automation else "text"),
        log_level=log_level,
    )


DEFAULT_SETTINGS = make_settings()
DEFAULT_DEPENDENCIES = Dependencies(settings=DEFAULT_SETTINGS)
JSON_DEPENDENCIES = Dependencies(settings=make_settings(format_name="json"))
AUTOMATION_DEPENDENCIES = Dependencies(settings=make_settings(automation=True))


def read_state(project: Path) -> ProjectState:
    """Read the project's stored selection/state."""
    return prepare_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    """Map every file under the project to its bytes."""
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


@dataclass
class Seed:
    """Create plan/task/context/doc documents with a fixed timestamp."""

    def plan(
        self,
        project: Path,
        name: str,
        *,
        status: PlanStatus = "draft",
        summary: str | None = None,
        body: str = "",
    ) -> Plan:
        return prepare_project(project).plans.create(
            name, PlanMetadata(created=_DEFAULT_CREATED, status=status, summary=summary), body
        )

    def task(  # noqa: PLR0913 -- helper mirrors the document options
        self,
        project: Path,
        plan: str,
        name: str,
        *,
        status: TaskStatus = "todo",
        summary: str | None = None,
        body: str = "",
    ) -> Task:
        return prepare_project(project).tasks.create(
            plan, name, TaskMetadata(created=_DEFAULT_CREATED, status=status, summary=summary), body
        )

    def context(
        self,
        project: Path,
        plan: str,
        name: str,
        *,
        summary: str | None = None,
        body: str = "",
    ) -> Context:
        return prepare_project(project).contexts.create(
            plan, name, ContextMetadata(created=_DEFAULT_CREATED, summary=summary), body
        )

    def doc(
        self,
        project: Path,
        name: str,
        *,
        summary: str | None = None,
        body: str = "",
    ) -> Doc:
        return prepare_project(project).docs.create(
            name, DocMetadata(created=_DEFAULT_CREATED, summary=summary), body
        )


seed = Seed()


class CLI:
    """Invoke the CLI under test with explicit settings and parse structured output."""

    def run(self, args: list[str], *, dependencies: Dependencies | None = None) -> Result:
        active = dependencies if dependencies is not None else DEFAULT_DEPENDENCIES
        return runner.invoke(create_cli(active), args)

    def json(
        self,
        result_type: type[ModelT],
        args: list[str],
        *,
        dependencies: Dependencies | None = None,
        expect: int = 0,
    ) -> ModelT:
        result = self.run(args, dependencies=dependencies)
        assert result.exit_code == expect, result.output + result.stderr
        return result_type.model_validate(json.loads(result.stdout))

    def error(
        self,
        args: list[str],
        *,
        dependencies: Dependencies | None = None,
        expect: int = 1,
    ) -> ErrorResult:
        result = self.run(args, dependencies=dependencies)
        assert result.exit_code == expect, result.output + result.stderr
        assert result.stdout == ""
        return ErrorResult.model_validate_json(result.stderr)


cli = CLI()
