import json
from datetime import UTC, datetime
from pathlib import Path
from typing import override
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.formatting import Formatter
from machinate.cli.models import CommandResult, ErrorResult, PathResult
from machinate.cli.project_setup import prepare_project
from machinate.storage import (
    ContextMetadata,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
    TaskMetadata,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example")
    )
    prepare_project(root).plans.create(
        "auth", PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )
    return root


def read_state(project: Path) -> ProjectState:
    return prepare_project(project).plans.project_state_store.read()


def seed_task(project: Path, name: str) -> None:
    prepare_project(project).tasks.create(
        "auth", name, TaskMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )


def seed_context(project: Path, name: str) -> None:
    prepare_project(project).contexts.create(
        "auth", name, ContextMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )


def test_plan_path_explicit(project: Path) -> None:
    result = runner.invoke(
        app, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.command == "plan path"
    assert parsed.project.name == "example"
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan == "auth"
    assert parsed.path == project / ".machi/plans/auth/plan.md"
    assert parsed.kind == "plan"
    assert parsed.exists is True
    assert read_state(project).current_plan is None


def test_plan_path_text_is_bare_path(project: Path) -> None:
    result = runner.invoke(app, ["plan", "path", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert result.stdout == f"{project / '.machi/plans/auth/plan.md'}\n"


def test_plan_path_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["plan", "path", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert PathResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_plan_path_does_not_change_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(
        app, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


def test_plan_path_automation_requires_plan(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["plan", "path", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "plan path"
    assert "Automation mode requires an explicit plan" in error.error


def test_plan_path_no_current_plan(project: Path) -> None:
    result = runner.invoke(app, ["plan", "path", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No current plan is selected" in ErrorResult.model_validate_json(result.stderr).error


def test_plan_path_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["plan", "path", "-p", "nope", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "plan path"


def test_task_path_document(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "path", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.command == "task path"
    assert parsed.kind == "task"
    assert parsed.path == project / ".machi/plans/auth/tasks/login.md"
    assert parsed.exists is True


def test_task_path_directory_absent(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.kind == "tasks_directory"
    assert parsed.path == project / ".machi/plans/auth/tasks"
    assert parsed.exists is False


def test_task_path_directory_exists(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.kind == "tasks_directory"
    assert parsed.exists is True


def test_task_path_unknown_task(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "path", "nope", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "nope" in ErrorResult.model_validate_json(result.stderr).error


def test_task_path_directory_never_creates(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert not (project / ".machi/plans/auth/tasks").exists()


def test_context_path_document(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(
        app, ["context", "path", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.command == "context path"
    assert parsed.kind == "context"
    assert parsed.path == project / ".machi/plans/auth/context/spec.md"
    assert parsed.exists is True


def test_context_path_directory_absent(project: Path) -> None:
    result = runner.invoke(
        app, ["context", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.kind == "context_directory"
    assert parsed.path == project / ".machi/plans/auth/context"
    assert parsed.exists is False


def test_context_path_directory_exists(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(
        app, ["context", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert PathResult.model_validate(json.loads(result.stdout)).exists is True


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_path_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], PathResult)


def test_task_path_help() -> None:
    result = runner.invoke(app, ["task", "path", "--help"])
    assert result.exit_code == 0
    assert "[NAME]" in result.stdout


def test_path_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "json")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)), ["plan", "path", "--unknown"]
    )
    assert result.exit_code == 2, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "plan path"
    factory.assert_not_called()


def test_path_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    factory = Mock(return_value=application)
    get = Mock(wraps=application.plans.get)
    monkeypatch.setattr(application.plans, "get", get)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    get.assert_called_once_with("auth")
