"""Reusable test harness pieces: document seeding and structured CLI invocation.

These live outside ``conftest.py`` so test modules import them by name instead of
importing pytest's special ``conftest`` module. Only fixtures that need ``tmp_path``
or per-test patching stay in ``tests/conftest.py``.
"""

import os
from pathlib import Path, PurePosixPath
from typing import TypeVar

from click.testing import Result
from pydantic import BaseModel
from typer.testing import CliRunner

from machinate.cli.cli import build_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult
from machinate.cli.project_setup import open_project
from machinate.cli.settings import Settings
from machinate.models.documents import (
    ContextMetadata,
    DocMetadata,
    LoadedDocument,
    LoadedPlan,
    Metadata,
    ParsedDocument,
    PlanStatus,
    TaskMetadata,
    TaskStatus,
)
from machinate.models.operations import CreateInput, StatusCreateInput
from machinate.storage import ProjectState
from machinate.storage.document_store import DocumentStore

runner = CliRunner()
ModelT = TypeVar("ModelT", bound=BaseModel)


def filtered_environment() -> dict[str, str]:
    """Return a copy of the environment without Machinate or agent variables."""
    return {
        key: value
        for key, value in os.environ.items()
        if key != "AI_AGENT" and not key.startswith("MACHI_")
    }


def make_settings(
    *,
    ai_agent: str | None = None,
    format_name: str | None = None,
) -> Settings:
    """Build settings for tests, leaving the format for ``Settings`` to resolve."""
    data: dict[str, object] = {}
    if ai_agent is not None:
        data["ai_agent"] = ai_agent
    if format_name is not None:
        data["format"] = format_name
    return Settings.model_validate(data)


DEFAULT_SETTINGS = make_settings()
DEFAULT_DEPENDENCIES = Dependencies(settings=DEFAULT_SETTINGS)
JSON_DEPENDENCIES = Dependencies(settings=make_settings(format_name="json"))
AGENT_DEPENDENCIES = Dependencies(settings=make_settings(ai_agent="test-agent"))


def read_state(project: Path) -> ProjectState:
    """Read the project's stored selection/state."""
    return open_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    """Map every file under the project to its bytes."""
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def _write_body(store: DocumentStore, path: PurePosixPath, metadata: Metadata, body: str) -> None:
    store.write(path, ParsedDocument(metadata=metadata, body=body))


def seed_plan(
    project: Path,
    name: str,
    *,
    status: PlanStatus = "draft",
    summary: str | None = None,
    body: str = "",
) -> LoadedPlan:
    service = open_project(project).plans
    loaded = service.create(name, StatusCreateInput[PlanStatus](status=status, summary=summary))
    if body:
        _write_body(service.document_store, loaded.record.path, loaded.record.metadata, body)
        loaded = loaded.model_copy(update={"body": body})
    return loaded


def seed_task(  # noqa: PLR0913 -- helper mirrors the document options
    project: Path,
    plan: str,
    name: str,
    *,
    status: TaskStatus = "todo",
    summary: str | None = None,
    body: str = "",
) -> LoadedDocument[TaskMetadata]:
    service = open_project(project).tasks
    batch = service.create_many(
        plan, [name], StatusCreateInput[TaskStatus](status=status, summary=summary)
    )
    loaded = LoadedDocument(record=batch.created[0], body="")
    if body:
        _write_body(service.document_store, loaded.record.path, loaded.record.metadata, body)
        loaded = loaded.model_copy(update={"body": body})
    return loaded


def seed_context(
    project: Path,
    plan: str,
    name: str,
    *,
    summary: str | None = None,
    body: str = "",
) -> LoadedDocument[ContextMetadata]:
    service = open_project(project).contexts
    batch = service.create_many(plan, [name], CreateInput(summary=summary))
    loaded = LoadedDocument(record=batch.created[0], body="")
    if body:
        _write_body(service.document_store, loaded.record.path, loaded.record.metadata, body)
        loaded = loaded.model_copy(update={"body": body})
    return loaded


def seed_doc(
    project: Path,
    name: str,
    *,
    summary: str | None = None,
    body: str = "",
) -> LoadedDocument[DocMetadata]:
    service = open_project(project).docs
    batch = service.create_many([name], CreateInput(summary=summary))
    loaded = LoadedDocument(record=batch.created[0], body="")
    if body:
        _write_body(service.document_store, loaded.record.path, loaded.record.metadata, body)
        loaded = loaded.model_copy(update={"body": body})
    return loaded


class CLI:
    """Invoke the CLI under test with explicit settings and parse structured output."""

    def run(self, args: list[str], *, dependencies: Dependencies | None = None) -> Result:
        active = dependencies if dependencies is not None else DEFAULT_DEPENDENCIES
        return runner.invoke(build_cli(active), args)

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
        code: str,
        dependencies: Dependencies | None = None,
        expect: int = 1,
    ) -> ErrorResult:
        result = self.run(args, dependencies=dependencies)
        assert result.exit_code == expect, result.output + result.stderr
        assert result.stdout == ""
        error = ErrorResult.model_validate_json(result.stderr)
        assert error.code == code, error
        return error


cli = CLI()
