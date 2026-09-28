import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult, PathResult
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
    ProjectStateStore(root / ".machi/machinate.toml").write(ProjectState(project_name="example"))
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


def test_path_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    factory = Mock(return_value=application)
    path = Mock(wraps=application.plans.path)
    monkeypatch.setattr(application.plans, "path", path)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    path.assert_called_once_with("auth")


def test_plan_path_ignores_malformed_contents(project: Path) -> None:
    (project / ".machi/plans/auth/plan.md").write_text("---\nnot: [valid\n---\nbody\n")
    result = runner.invoke(
        app, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.path == project / ".machi/plans/auth/plan.md"
    assert parsed.exists is True


def test_task_path_ignores_malformed_contents(project: Path) -> None:
    seed_task(project, "login")
    target = project / ".machi/plans/auth/tasks/login.md"
    target.write_text("---\nnot: [valid\n---\nbody\n")
    result = runner.invoke(
        app, ["task", "path", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.path == target
    assert parsed.exists is True


def test_context_path_ignores_malformed_contents(project: Path) -> None:
    seed_context(project, "spec")
    target = project / ".machi/plans/auth/context/spec.md"
    target.write_text("---\nnot: [valid\n---\nbody\n")
    result = runner.invoke(
        app, ["context", "path", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = PathResult.model_validate(json.loads(result.stdout))
    assert parsed.path == target
    assert parsed.exists is True
