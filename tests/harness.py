"""Reusable test harness pieces: document seeding and structured CLI invocation.

These live outside ``conftest.py`` so test modules import them by name instead of
importing pytest's special ``conftest`` module. Only fixtures that need ``tmp_path``
or per-test patching stay in ``tests/conftest.py``.
"""

import os
from dataclasses import dataclass
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
from machinate.models.documents import (
    ContextMetadata,
    DocMetadata,
    LoadedDocument,
    LoadedPlan,
    ParsedDocument,
    PlanStatus,
    TaskMetadata,
    TaskStatus,
)
from machinate.models.operations import CreateInput, StatusCreateInput
from machinate.storage import ProjectState

runner = CliRunner()
ModelT = TypeVar("ModelT", bound=BaseModel)


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
    ai_agent: str | None = None,
    format_name: str | None = None,
    log_level: LogLevel | None = None,
) -> Settings:
    """Build settings with every field explicit, so the environment cannot leak in."""
    return Settings(
        ai_agent=ai_agent,
        format=format_name if format_name is not None else ("json" if ai_agent else "text"),
        log_level=log_level,
    )


DEFAULT_SETTINGS = make_settings()
DEFAULT_DEPENDENCIES = Dependencies(settings=DEFAULT_SETTINGS)
JSON_DEPENDENCIES = Dependencies(settings=make_settings(format_name="json"))
AGENT_DEPENDENCIES = Dependencies(settings=make_settings(ai_agent="test-agent"))


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
    ) -> LoadedPlan:
        service = prepare_project(project).plans
        loaded = service.create(name, StatusCreateInput[PlanStatus](status=status, summary=summary))
        if body:
            service.document_store.write(
                service.path(name), ParsedDocument(metadata=loaded.record.metadata, body=body)
            )
            return loaded.model_copy(update={"body": body})
        return loaded

    def task(  # noqa: PLR0913 -- helper mirrors the document options
        self,
        project: Path,
        plan: str,
        name: str,
        *,
        status: TaskStatus = "todo",
        summary: str | None = None,
        body: str = "",
    ) -> LoadedDocument[TaskMetadata]:
        service = prepare_project(project).tasks
        loaded = service.create(
            plan, name, StatusCreateInput[TaskStatus](status=status, summary=summary)
        )
        if body:
            service.document_store.write(
                service.path(plan, name),
                ParsedDocument(metadata=loaded.record.metadata, body=body),
            )
            return loaded.model_copy(update={"body": body})
        return loaded

    def context(
        self,
        project: Path,
        plan: str,
        name: str,
        *,
        summary: str | None = None,
        body: str = "",
    ) -> LoadedDocument[ContextMetadata]:
        service = prepare_project(project).contexts
        loaded = service.create(plan, name, CreateInput(summary=summary))
        if body:
            service.document_store.write(
                service.path(plan, name),
                ParsedDocument(metadata=loaded.record.metadata, body=body),
            )
            return loaded.model_copy(update={"body": body})
        return loaded

    def doc(
        self,
        project: Path,
        name: str,
        *,
        summary: str | None = None,
        body: str = "",
    ) -> LoadedDocument[DocMetadata]:
        service = prepare_project(project).docs
        loaded = service.create(name, CreateInput(summary=summary))
        if body:
            service.document_store.write(
                service.path(name), ParsedDocument(metadata=loaded.record.metadata, body=body)
            )
            return loaded.model_copy(update={"body": body})
        return loaded


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
        return result_type.model_validate_json(result.stdout)

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
