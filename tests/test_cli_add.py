import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, override
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.formatting import Formatter
from machinate.cli.models import AddResult, CommandResult, ErrorResult, ListResult
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


def read_state(project: Path) -> ProjectState:
    return prepare_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def test_add_explicit_project(project: Path) -> None:
    result = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = AddResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan.name == "alpha"
    assert parsed.plan.path.as_posix() == "plans/alpha/plan.md"
    assert parsed.plan.document.metadata.status == "draft"
    assert parsed.plan.document.metadata.created.tzinfo is not None
    assert parsed.plan.document.body == ""
    assert (project / ".machi/plans/alpha/plan.md").is_file()
    assert read_state(project).current_plan is None


def test_add_current_directory(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["plan", "add", "alpha", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert AddResult.model_validate(json.loads(result.stdout)).project.directory == project


def test_add_never_changes_selection(project: Path) -> None:
    prepare_project(project).plans.create(
        "existing", PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )
    prepare_project(project).plans.set_current("existing")
    result = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "existing"


def test_add_duplicate_preserves_existing(project: Path) -> None:
    first = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    assert first.exit_code == 0, first.output
    before = snapshot(project)
    duplicate = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    assert duplicate.exit_code == 1, duplicate.output
    error = ErrorResult.model_validate_json(duplicate.stderr)
    assert error.project is not None
    assert "alpha/plan.md" in error.error
    assert snapshot(project) == before


@pytest.mark.parametrize("invalid", ["../bad", "a/b", "a\\b", "a:b", "", ".", ".."])
def test_add_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    before = snapshot(project)
    result = runner.invoke(app, ["plan", "add", invalid, "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_add_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    result = runner.invoke(app, ["plan", "add", "alpha", "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


def test_add_missing_project_directory(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    result = runner.invoke(app, ["plan", "add", "alpha", "-P", str(missing), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No initialized project at" in ErrorResult.model_validate_json(result.stderr).error
    assert not missing.exists()


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_add_output(project: Path, format_name: str) -> None:
    result = runner.invoke(
        app, ["plan", "add", "alpha", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert AddResult.model_validate(json.loads(result.stdout)).plan.name == "alpha"
    else:
        assert "Created plan alpha in example" in result.stdout
        assert str(project / ".machi/plans/alpha/plan.md") in result.stdout


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
def test_add_format_precedence(  # noqa: PLR0913
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    interactive: str | None,
    env_format: str | None,
    flag: str | None,
    expected: str,
) -> None:
    if interactive is not None:
        monkeypatch.setenv("MACHI_INTERACTIVE", interactive)
    if env_format is not None:
        monkeypatch.setenv("MACHI_FORMAT", env_format)
    args = ["plan", "add", "alpha", "-P", str(project)]
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
def test_add_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_add_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["plan", "add", "alpha", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], AddResult)
    result = runner.invoke(
        custom, ["plan", "add", "alpha", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 1
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[1], ErrorResult)


def test_add_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed = application.plans.create("seed", PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC)))
    create = Mock(return_value=seed)
    monkeypatch.setattr(application.plans, "create", create)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["plan", "add", "alpha", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    create.assert_called_once()
    call_name, call_metadata = cast("tuple[str, PlanMetadata]", create.call_args.args)
    assert call_name == "alpha"
    assert call_metadata.status == "draft"
    assert call_metadata.created.tzinfo is not None
    assert AddResult.model_validate(json.loads(result.stdout)).plan.name == "seed"


def test_add_stamps_aware_utc(project: Path) -> None:
    before = datetime.now(UTC)
    result = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    after = datetime.now(UTC)
    assert result.exit_code == 0, result.output
    created = AddResult.model_validate(json.loads(result.stdout)).plan.document.metadata.created
    assert created.tzinfo is not None
    assert before <= created <= after


def test_add_then_list(project: Path) -> None:
    added = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    assert added.exit_code == 0, added.output
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert [plan.name for plan in ListResult.model_validate(json.loads(result.stdout)).plans] == [
        "alpha"
    ]


def test_add_help() -> None:
    result = runner.invoke(app, ["plan", "add", "--help"])
    assert result.exit_code == 0
    assert "--project" in result.stdout
    assert "--format" in result.stdout
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_add_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["plan", "add", "alpha"]
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
    assert "--unknown" in ErrorResult.model_validate_json(result.stderr).error
    factory.assert_not_called()


def test_add_parser_error_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["plan", "add", "alpha", "--unknown", "--format=custom"])
    assert result.exit_code == 2
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[0], ErrorResult)
