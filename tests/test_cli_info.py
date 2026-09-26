import json
import subprocess
import sys
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
from machinate.cli.models import CommandResult, ErrorResult, InfoResult
from machinate.cli.project_setup import prepare_project
from machinate.models.plan import PlanOverview, ProjectOverview
from machinate.storage import (
    ContextMetadata,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
    TaskMetadata,
)

runner = CliRunner()

_CREATED = datetime(2026, 1, 1, tzinfo=UTC)


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
    context = prepare_project(root)
    context.plans.create("auth", PlanMetadata(created=_CREATED))
    context.plans.create("billing", PlanMetadata(created=_CREATED, status="active"))
    context.tasks.create("auth", "design", TaskMetadata(created=_CREATED, status="done"))
    context.tasks.create("auth", "implement", TaskMetadata(created=_CREATED))
    context.contexts.create("auth", "spec", ContextMetadata(created=_CREATED))
    return root


def seed_plan(project: Path, name: str) -> None:
    prepare_project(project).plans.create(name, PlanMetadata(created=_CREATED))


def test_info_project_overview(project: Path) -> None:
    result = runner.invoke(app, ["info", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = InfoResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert isinstance(parsed.overview, ProjectOverview)
    overview = parsed.overview
    assert overview.current_plan is None
    assert overview.selection_valid is True
    assert overview.plan_count == 2
    assert overview.plans_by_status == {"draft": 1, "active": 1, "done": 0}
    assert overview.task_totals == {"todo": 1, "in-progress": 0, "done": 1}
    assert overview.context_count == 1
    assert {plan.name for plan in overview.recent_plans} == {"auth", "billing"}


def test_info_project_overview_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["info", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    overview = InfoResult.model_validate(json.loads(result.stdout)).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.current_plan == "auth"
    assert overview.selection_valid is True


def test_info_project_overview_stale_selection(project: Path) -> None:
    ProjectStateStore(UPath(project / ".machi/machinate.toml")).write(
        ProjectState(project_name="example", current_plan="ghost")
    )
    result = runner.invoke(app, ["info", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    overview = InfoResult.model_validate(json.loads(result.stdout)).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.current_plan == "ghost"
    assert overview.selection_valid is False


def test_info_project_overview_limits_recent_plans(tmp_path: Path) -> None:
    root = tmp_path / "project"
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example")
    )
    for index in range(6):
        seed_plan(root, f"plan{index}")
    result = runner.invoke(app, ["info", "-P", str(root), "--format", "json"])
    assert result.exit_code == 0, result.output
    overview = InfoResult.model_validate(json.loads(result.stdout)).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.plan_count == 6
    assert len(overview.recent_plans) == 5


def test_info_empty_project(tmp_path: Path) -> None:
    root = tmp_path / "project"
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example")
    )
    result = runner.invoke(app, ["info", "-P", str(root), "--format", "json"])
    assert result.exit_code == 0, result.output
    overview = InfoResult.model_validate(json.loads(result.stdout)).overview
    assert isinstance(overview, ProjectOverview)
    assert overview.plan_count == 0
    assert overview.recent_plans == []


def test_info_plan_overview(project: Path) -> None:
    result = runner.invoke(app, ["info", "-p", "auth", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = InfoResult.model_validate(json.loads(result.stdout))
    assert isinstance(parsed.overview, PlanOverview)
    overview = parsed.overview
    assert overview.current is False
    assert overview.info.plan.name == "auth"
    assert overview.info.task_counts == {"todo": 1, "in-progress": 0, "done": 1}
    assert overview.info.context_count == 1


def test_info_plan_overview_current(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["info", "-p", "auth", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    overview = InfoResult.model_validate(json.loads(result.stdout)).overview
    assert isinstance(overview, PlanOverview)
    assert overview.current is True


def test_info_never_uses_current_without_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("billing")
    result = runner.invoke(app, ["info", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    overview = InfoResult.model_validate(json.loads(result.stdout)).overview
    assert overview.kind == "project"


def test_info_unknown_plan(project: Path) -> None:
    result = runner.invoke(app, ["info", "-p", "nope", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "info"
    assert "nope" in error.error


def test_info_invalid_plan_name(project: Path) -> None:
    result = runner.invoke(app, ["info", "-p", "../bad", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Expected a nonempty name" in error.error


def test_info_text_project_overview(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["info", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "Project example" in result.stdout
    assert "Current plan: auth" in result.stdout
    assert "Plans: 2 (draft: 1, active: 1, done: 0)" in result.stdout
    assert "Tasks: 2 (todo: 1, in-progress: 0, done: 1)" in result.stdout
    assert "Contexts: 1" in result.stdout
    assert "Recent plans:" in result.stdout


def test_info_text_project_overview_without_current(project: Path) -> None:
    result = runner.invoke(app, ["info", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "Current plan: (none)" in result.stdout


def test_info_text_plan_overview(project: Path) -> None:
    result = runner.invoke(app, ["info", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "Plan auth (draft)" in result.stdout
    assert "Tasks: 2 (todo: 1, in-progress: 0, done: 1)" in result.stdout
    assert "Contexts: 1" in result.stdout


def test_info_help() -> None:
    result = runner.invoke(app, ["info", "--help"])
    assert result.exit_code == 0
    assert "--plan" in result.stdout
    assert not result.stdout.startswith("{")


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_info_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["info", "-p", "auth", "-P", str(project), "--format", "custom"])
    assert result.exit_code == 0, result.output
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], InfoResult)


def test_info_missing_project_directory_error_is_rendered(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    result = runner.invoke(app, ["info", "-P", str(missing), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "No initialized project" in error.error
    assert str(missing) in error.error


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_info_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["info"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "info"
    factory.assert_not_called()


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_checkout_executable_info(tmp_path: Path, executable: str) -> None:
    launcher = Path(sys.executable).with_name(executable)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    commands = [
        ["init", "-P", str(fresh), "--format", "json"],
        ["add", "auth", "-P", str(fresh), "--format", "json"],
    ]
    for args in commands:
        completed = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
            [str(launcher), *args], capture_output=True, text=True, check=False
        )
        assert completed.returncode == 0, completed.stderr
    for args in (
        ["info", "-P", str(fresh), "--format", "json"],
        ["info", "-p", "auth", "-P", str(fresh), "--format", "json"],
    ):
        completed = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
            [str(launcher), *args], capture_output=True, text=True, check=False
        )
        assert completed.returncode == 0, completed.stderr
        parsed = InfoResult.model_validate(json.loads(completed.stdout))
        assert parsed.command == "info"
