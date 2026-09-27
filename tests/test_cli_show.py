import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult, ShowResult
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
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example")
    )
    return root


def seed_plan(project: Path, name: str = "auth", *, current: bool = False) -> None:
    application = prepare_project(project)
    application.plans.create(
        name,
        PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC)),
        body="# Auth\n\nDetails",
    )
    if current:
        application.plans.set_current(name)


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def test_show_explicit_plan(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(
        app, ["plan", "show", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = ShowResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan.name == "auth"
    assert parsed.plan.path.as_posix() == "plans/auth/plan.md"
    assert parsed.plan.document.metadata.status == "draft"
    assert parsed.plan.document.get_or_derive_summary() == "Details"
    assert parsed.plan.document.body == "# Auth\n\nDetails"


def test_show_current_plan(project: Path) -> None:
    seed_plan(project, current=True)
    result = runner.invoke(app, ["plan", "show", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ShowResult.model_validate(json.loads(result.stdout)).plan.name == "auth"


def test_show_current_directory(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project)
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["plan", "show", "-p", "auth", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ShowResult.model_validate(json.loads(result.stdout)).project.directory == project


def test_show_discovers_upward(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project)
    child = project / "nested"
    child.mkdir()
    monkeypatch.chdir(child)
    result = runner.invoke(app, ["plan", "show", "-p", "auth", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ShowResult.model_validate(json.loads(result.stdout)).project.directory == project


def test_show_no_current_plan(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(app, ["plan", "show", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert "No current plan" in result.stderr


def test_show_automation_requires_plan(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project, current=True)
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["plan", "show", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Automation mode requires an explicit plan" in error.error


def test_show_missing_plan_preserves_state(project: Path) -> None:
    seed_plan(project, current=True)
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "show", "-p", "absent", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.project is not None
    assert "absent/plan.md" in error.error
    assert snapshot(project) == before
    assert prepare_project(project).plans.project_state_store.read().current_plan == "auth"


@pytest.mark.parametrize("invalid", ["../bad", "a/b", "a\\b", "a:b", "", ".", ".."])
def test_show_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "show", "-p", invalid, "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_show_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    result = runner.invoke(app, ["plan", "show", "-p", "auth", "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_show_output(project: Path, format_name: str) -> None:
    seed_plan(project)
    result = runner.invoke(
        app, ["plan", "show", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert ShowResult.model_validate(json.loads(result.stdout)).plan.name == "auth"
    else:
        assert "Plan auth (draft)" in result.stdout
        assert "Project: example" in result.stdout
        assert str(project / ".machi/plans/auth/plan.md") in result.stdout
        assert "# Auth" in result.stdout
        assert "Details" in result.stdout


def test_show_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed_plan(project)
    plan = application.plans.get("auth")
    get = Mock(return_value=plan)
    monkeypatch.setattr(application.plans, "get", get)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "show", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    get.assert_called_once_with("auth")
    assert ShowResult.model_validate(json.loads(result.stdout)).plan.name == "auth"


def test_show_delegation_uses_current(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed_plan(project, current=True)
    plan = application.plans.get("auth")
    get_current = Mock(return_value=plan)
    monkeypatch.setattr(application.plans, "get_current", get_current)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=Mock(return_value=application))),
        ["plan", "show", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    get_current.assert_called_once_with()
    assert ShowResult.model_validate(json.loads(result.stdout)).plan.name == "auth"
