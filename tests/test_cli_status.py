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
from machinate.cli.models import CommandResult, ErrorResult, StatusResult
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


def seed_plan(project: Path, name: str = "auth", *, current: bool = False) -> None:
    application = prepare_project(project)
    application.plans.create(name, PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC)))
    if current:
        application.plans.set_current(name)


def read_status(project: Path, name: str = "auth") -> str:
    return prepare_project(project).plans.get(name).document.metadata.status


def read_state(project: Path) -> ProjectState:
    return prepare_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def test_status_reads_explicit(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(
        app, ["plan", "status", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = StatusResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.plan.name == "auth"
    assert parsed.plan.document.metadata.status == "draft"


def test_status_reads_current(project: Path) -> None:
    seed_plan(project, current=True)
    result = runner.invoke(app, ["plan", "status", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert StatusResult.model_validate(json.loads(result.stdout)).plan.name == "auth"


def test_status_non_interactive_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_plan(project, current=True)
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["plan", "status", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Non-interactive mode requires an explicit plan" in error.error


@pytest.mark.parametrize("value", ["draft", "active", "done"])
def test_status_sets_explicit(project: Path, value: str) -> None:
    seed_plan(project)
    result = runner.invoke(
        app, ["plan", "status", value, "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert (
        StatusResult.model_validate(json.loads(result.stdout)).plan.document.metadata.status
        == value
    )
    assert read_status(project) == value


def test_status_sets_current(project: Path) -> None:
    seed_plan(project, current=True)
    result = runner.invoke(app, ["plan", "status", "done", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_status(project) == "done"
    assert read_state(project).current_plan == "auth"


def test_status_sets_non_interactive_explicit(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_plan(project)
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["plan", "status", "active", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert read_status(project) == "active"


def test_status_invalid_value_preserves_plan(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "status", "nope", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Unknown status 'nope'" in error.error
    assert "draft, active, done" in error.error
    assert read_status(project) == "draft"
    assert snapshot(project) == before


def test_status_missing_plan_preserves_state(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "status", "active", "-p", "absent", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.project is not None
    assert "absent/plan.md" in error.error
    assert snapshot(project) == before


def test_status_invalid_name_preserves_target(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "status", "active", "-p", "../bad", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_status_read_is_read_only(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "status", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert snapshot(project) == before


def test_status_only_changes_selected_plan(project: Path) -> None:
    seed_plan(project, "auth")
    seed_plan(project, "other")
    other_before = (project / ".machi/plans/other/plan.md").read_bytes()
    state_before = (project / ".machi/machinate.toml").read_bytes()
    result = runner.invoke(
        app, ["plan", "status", "active", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_status(project, "auth") == "active"
    assert read_status(project, "other") == "draft"
    assert (project / ".machi/plans/other/plan.md").read_bytes() == other_before
    assert (project / ".machi/machinate.toml").read_bytes() == state_before


def test_status_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    result = runner.invoke(app, ["plan", "status", "-p", "auth", "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_status_output(project: Path, format_name: str) -> None:
    seed_plan(project)
    result = runner.invoke(
        app, ["plan", "status", "active", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert StatusResult.model_validate(json.loads(result.stdout)).plan.name == "auth"
    else:
        assert "Selected" not in result.stdout
        assert "Plan auth is active in example" in result.stdout


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
def test_status_format_precedence(  # noqa: PLR0913
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    interactive: str | None,
    env_format: str | None,
    flag: str | None,
    expected: str,
) -> None:
    seed_plan(project)
    if interactive is not None:
        monkeypatch.setenv("MACHI_INTERACTIVE", interactive)
    if env_format is not None:
        monkeypatch.setenv("MACHI_FORMAT", env_format)
    args = ["plan", "status", "-p", "auth", "-P", str(project)]
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
def test_status_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    seed_plan(project)
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["plan", "status", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_status_formatter_injection(project: Path) -> None:
    seed_plan(project)
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["plan", "status", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], StatusResult)
    result = runner.invoke(
        custom, ["plan", "status", "nope", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 1
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[1], ErrorResult)


def test_status_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project)
    application = prepare_project(project)
    plan = application.plans.get("auth")
    set_status = Mock(return_value=plan)
    monkeypatch.setattr(application.plans, "set_status", set_status)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "status", "active", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    set_status.assert_called_once_with("auth", "active")
    assert StatusResult.model_validate(json.loads(result.stdout)).plan.name == "auth"


def test_status_does_not_change_selection(project: Path) -> None:
    seed_plan(project, "auth", current=True)
    seed_plan(project, "other")
    result = runner.invoke(
        app, ["plan", "status", "done", "-p", "other", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_status(project, "other") == "done"
    assert read_state(project).current_plan == "auth"


def test_status_help() -> None:
    result = runner.invoke(app, ["plan", "status", "--help"])
    assert result.exit_code == 0
    assert "--plan" in result.stdout
    assert "--project" in result.stdout
    assert "--format" in result.stdout
    assert "New status" in result.stdout
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_status_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["plan", "status", "active", "-p", "auth"]
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
    assert error.command == "plan status"
    assert "--unknown" in error.error
    factory.assert_not_called()
