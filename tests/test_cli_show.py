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
from machinate.cli.models import CommandResult, ErrorResult, ListResult, ShowResult
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
    application.plans.create(
        name,
        PlanMetadata(
            created=datetime(2026, 1, 1, tzinfo=UTC),
            summary="Authentication",
        ),
        body="# Auth\n\nDetails",
    )
    if current:
        application.plans.set_current(name)


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def test_show_explicit_plan(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(app, ["show", "-p", "auth", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = ShowResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan.name == "auth"
    assert parsed.plan.path.as_posix() == "auth/plan.md"
    assert parsed.plan.document.metadata.status == "draft"
    assert parsed.plan.document.metadata.summary == "Authentication"
    assert parsed.plan.document.body == "# Auth\n\nDetails"


def test_show_current_plan(project: Path) -> None:
    seed_plan(project, current=True)
    result = runner.invoke(app, ["show", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ShowResult.model_validate(json.loads(result.stdout)).plan.name == "auth"


def test_show_current_directory(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project)
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["show", "-p", "auth", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ShowResult.model_validate(json.loads(result.stdout)).project.directory == project


def test_show_discovers_upward(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project)
    child = project / "nested"
    child.mkdir()
    monkeypatch.chdir(child)
    result = runner.invoke(app, ["show", "-p", "auth", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ShowResult.model_validate(json.loads(result.stdout)).project.directory == project


def test_show_no_current_plan(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(app, ["show", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert "No current plan" in result.stderr


def test_show_non_interactive_requires_plan(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project, current=True)
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["show", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Non-interactive mode requires an explicit plan" in error.error


def test_show_missing_plan_preserves_state(project: Path) -> None:
    seed_plan(project, current=True)
    before = snapshot(project)
    result = runner.invoke(app, ["show", "-p", "absent", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.project is not None
    assert "absent/plan.md" in error.error
    assert snapshot(project) == before
    assert prepare_project(project).plans.project_state_store.read().current_plan == "auth"


def test_show_is_read_only(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(app, ["show", "-p", "auth", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert snapshot(project) == before


@pytest.mark.parametrize("invalid", ["../bad", "a/b", "a\\b", "a:b", "", ".", ".."])
def test_show_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(app, ["show", "-p", invalid, "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_show_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    result = runner.invoke(app, ["show", "-p", "auth", "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_show_output(project: Path, format_name: str) -> None:
    seed_plan(project)
    result = runner.invoke(app, ["show", "-p", "auth", "-P", str(project), "--format", format_name])
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert ShowResult.model_validate(json.loads(result.stdout)).plan.name == "auth"
    else:
        assert "Plan auth (draft)" in result.stdout
        assert "Project: example" in result.stdout
        assert str(project / ".machi/auth/plan.md") in result.stdout
        assert "# Auth" in result.stdout
        assert "Details" in result.stdout


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
def test_show_format_precedence(  # noqa: PLR0913
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
    args = ["show", "-p", "auth", "-P", str(project)]
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
def test_show_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    seed_plan(project)
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["show", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_show_formatter_injection(project: Path) -> None:
    seed_plan(project)
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["show", "-p", "auth", "-P", str(project), "--format", "custom"])
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], ShowResult)
    result = runner.invoke(
        custom, ["show", "-p", "absent", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 1
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[1], ErrorResult)


def test_show_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed_plan(project)
    plan = application.plans.get("auth")
    get = Mock(return_value=plan)
    monkeypatch.setattr(application.plans, "get", get)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["show", "-p", "auth", "-P", str(project), "--format", "json"],
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
        ["show", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    get_current.assert_called_once_with()
    assert ShowResult.model_validate(json.loads(result.stdout)).plan.name == "auth"


def test_show_then_list(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(create_cli(), ["add", "second", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    shown = runner.invoke(app, ["show", "-p", "second", "-P", str(project), "--format", "json"])
    assert shown.exit_code == 0, shown.output
    listed = runner.invoke(app, ["list", "-P", str(project), "--format", "json"])
    assert listed.exit_code == 0, listed.output
    names = [plan.name for plan in ListResult.model_validate(json.loads(listed.stdout)).plans]
    assert names == ["auth", "second"]
    assert prepare_project(project).plans.project_state_store.read().current_plan is None


def test_show_help() -> None:
    result = runner.invoke(app, ["show", "--help"])
    assert result.exit_code == 0
    assert "--plan" in result.stdout
    assert "--project" in result.stdout
    assert "--format" in result.stdout
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_show_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["show", "-p", "auth"]
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
    assert error.command == "show"
    assert "--unknown" in error.error
    factory.assert_not_called()


def test_show_parser_error_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["show", "-p", "auth", "--unknown", "--format=custom"])
    assert result.exit_code == 2
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[0], ErrorResult)


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_checkout_executable_show(tmp_path: Path, executable: str) -> None:
    launcher = Path(sys.executable).with_name(executable)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    initialized = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "init", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert initialized.returncode == 0, initialized.stderr
    added = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "add", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert added.returncode == 0, added.stderr
    shown = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "show", "-p", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert shown.returncode == 0, shown.stderr
    assert ShowResult.model_validate(json.loads(shown.stdout)).plan.name == "auth"
    missing = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "show", "-p", "absent", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode == 1
    assert "absent/plan.md" in ErrorResult.model_validate_json(missing.stderr).error
    help_result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "show", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--plan" in help_result.stdout
