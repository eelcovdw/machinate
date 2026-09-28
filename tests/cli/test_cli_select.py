import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import (
    ErrorResult,
    SelectResult,
    ShowResult,
    UnselectResult,
)
from machinate.cli.project_setup import prepare_project
from machinate.storage import PlanMetadata, ProjectState, ProjectStateStore

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(root / ".machi/machinate.toml").write(ProjectState(project_name="example"))
    return root


def seed_plan(project: Path, name: str) -> None:
    prepare_project(project).plans.create(
        name, PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )


def read_state(project: Path) -> ProjectState:
    return prepare_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def test_select_explicit_plan(project: Path) -> None:
    seed_plan(project, "auth")
    result = runner.invoke(app, ["plan", "select", "auth", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = SelectResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.state.current_plan == "auth"
    assert read_state(project).current_plan == "auth"


def test_select_works_in_automation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project, "auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["plan", "select", "auth", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert SelectResult.model_validate(json.loads(result.stdout)).state.current_plan == "auth"
    assert read_state(project).current_plan == "auth"


def test_automation_mode_requires_explicit_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_plan(project, "auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["plan", "show", "-P", str(project)])
    assert result.exit_code == 1
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "plan show"
    assert "Automation mode requires an explicit plan" in error.error


def test_select_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    result = runner.invoke(app, ["plan", "select", "auth", "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_select_output(project: Path, format_name: str) -> None:
    seed_plan(project, "auth")
    result = runner.invoke(
        app, ["plan", "select", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert SelectResult.model_validate(json.loads(result.stdout)).state.current_plan == "auth"
    else:
        assert "Selected plan auth in example" in result.stdout


def test_select_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project, "auth")
    application = prepare_project(project)
    selected = ProjectState(project_name="example", current_plan="auth")
    set_current = Mock(return_value=selected)
    monkeypatch.setattr(application.plans, "set_current", set_current)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "select", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    set_current.assert_called_once_with("auth")
    assert SelectResult.model_validate(json.loads(result.stdout)).state.current_plan == "auth"


def test_select_then_show(project: Path) -> None:
    seed_plan(project, "auth")
    selected = runner.invoke(
        app, ["plan", "select", "auth", "-P", str(project), "--format", "json"]
    )
    assert selected.exit_code == 0, selected.output
    shown = runner.invoke(app, ["plan", "show", "-P", str(project), "--format", "json"])
    assert shown.exit_code == 0, shown.output
    assert ShowResult.model_validate(json.loads(shown.stdout)).plan.name == "auth"


def test_unselect_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project, "auth")
    application = prepare_project(project)
    cleared = ProjectState(project_name="example", current_plan=None)
    clear_current = Mock(return_value=cleared)
    monkeypatch.setattr(application.plans, "clear_current", clear_current)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "unselect", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    clear_current.assert_called_once_with()
    assert UnselectResult.model_validate(json.loads(result.stdout)).state.current_plan is None


def test_unselect_parser_errors_use_json() -> None:
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "unselect", "--unknown", "--format", "json"],
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert ErrorResult.model_validate_json(result.stderr).command == "plan unselect"
    factory.assert_not_called()
