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
from machinate.cli.models import CommandResult, ErrorResult, SetResult, ShowResult
from machinate.cli.project_setup import prepare_project
from machinate.storage import PlanMetadata, ProjectState, ProjectStateStore

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_INTERACTIVE", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example")
    )
    return root


def seed_plan(project: Path, name: str) -> None:
    prepare_project(project).plans.create(
        name, PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )


def read_state(project: Path) -> ProjectState:
    return prepare_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def test_set_explicit_plan(project: Path) -> None:
    seed_plan(project, "auth")
    result = runner.invoke(
        app, ["plan", "set", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = SetResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.state.current_plan == "auth"
    assert read_state(project).current_plan == "auth"


def test_set_works_non_interactive(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project, "auth")
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(
        app, ["plan", "set", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert SetResult.model_validate(json.loads(result.stdout)).state.current_plan == "auth"
    assert read_state(project).current_plan == "auth"


def test_set_requires_explicit_plan(project: Path) -> None:
    seed_plan(project, "auth")
    before = snapshot(project)
    result = runner.invoke(app, ["plan", "set", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert "explicit plan is required" in result.stderr
    assert read_state(project).current_plan is None
    assert snapshot(project) == before


def test_set_invalid_name_preserves_target(project: Path) -> None:
    seed_plan(project, "auth")
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "set", "-p", "../bad", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_set_missing_plan_preserves_state(project: Path) -> None:
    seed_plan(project, "auth")
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "set", "-p", "absent", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.project is not None
    assert "absent/plan.md" in error.error
    assert read_state(project).current_plan is None
    assert snapshot(project) == before


def test_set_only_changes_state(project: Path) -> None:
    seed_plan(project, "auth")
    seed_plan(project, "other")
    documents_before = {
        path: data for path, data in snapshot(project).items() if path.name == "plan.md"
    }
    result = runner.invoke(
        app, ["plan", "set", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    documents_after = {
        path: data for path, data in snapshot(project).items() if path.name == "plan.md"
    }
    assert documents_after == documents_before


def test_set_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    result = runner.invoke(app, ["plan", "set", "-p", "auth", "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_set_output(project: Path, format_name: str) -> None:
    seed_plan(project, "auth")
    result = runner.invoke(
        app, ["plan", "set", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert SetResult.model_validate(json.loads(result.stdout)).state.current_plan == "auth"
    else:
        assert "Selected plan auth in example" in result.stdout


@pytest.mark.parametrize(
    ("interactive", "env_format", "flag", "expected"),
    [
        (None, None, None, "text"),
        ("false", None, None, "json"),
        ("true", None, None, "text"),
        ("false", "text", None, "text"),
        (None, "json", None, "json"),
        ("false", "json", "text", "text"),
    ],
)
def test_set_format_precedence(  # noqa: PLR0913
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    interactive: str | None,
    env_format: str | None,
    flag: str | None,
    expected: str,
) -> None:
    seed_plan(project, "auth")
    if interactive is not None:
        monkeypatch.setenv("MACHI_INTERACTIVE", interactive)
    if env_format is not None:
        monkeypatch.setenv("MACHI_FORMAT", env_format)
    args = ["plan", "set", "-p", "auth", "-P", str(project)]
    if flag is not None:
        args.extend(["--format", flag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{") == (expected == "json")


@pytest.mark.parametrize(
    ("env_name", "env_value", "field"),
    [
        ("MACHI_INTERACTIVE", "perhaps", "interactive"),
        ("MACHI_FORMAT", "human", "format"),
    ],
)
def test_set_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    seed_plan(project, "auth")
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["plan", "set", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_set_formatter_injection(project: Path) -> None:
    seed_plan(project, "auth")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["plan", "set", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], SetResult)
    result = runner.invoke(
        custom, ["plan", "set", "-p", "absent", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 1
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[1], ErrorResult)


def test_set_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project, "auth")
    application = prepare_project(project)
    selected = ProjectState(project_name="example", current_plan="auth")
    set_current = Mock(return_value=selected)
    monkeypatch.setattr(application.plans, "set_current", set_current)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "set", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    set_current.assert_called_once_with("auth")
    assert SetResult.model_validate(json.loads(result.stdout)).state.current_plan == "auth"


def test_set_then_show(project: Path) -> None:
    seed_plan(project, "auth")
    selected = runner.invoke(
        app, ["plan", "set", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert selected.exit_code == 0, selected.output
    shown = runner.invoke(app, ["plan", "show", "-P", str(project), "--format", "json"])
    assert shown.exit_code == 0, shown.output
    assert ShowResult.model_validate(json.loads(shown.stdout)).plan.name == "auth"


def test_selection_does_not_redirect_explicit_operation(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_plan(project, "auth")
    seed_plan(project, "other")
    selected = runner.invoke(
        app, ["plan", "set", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert selected.exit_code == 0, selected.output
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    shown = runner.invoke(
        app, ["plan", "show", "-p", "other", "-P", str(project), "--format", "json"]
    )
    assert shown.exit_code == 0, shown.output
    assert ShowResult.model_validate(json.loads(shown.stdout)).plan.name == "other"
    assert read_state(project).current_plan == "auth"


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_set_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["plan", "set", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "plan set"
    assert "--unknown" in error.error
    factory.assert_not_called()
