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
from machinate.cli.models import CommandResult, ErrorResult, UpdateResult
from machinate.cli.project_setup import prepare_project
from machinate.models.plan import PlanUpdate
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


def read_metadata(project: Path, name: str = "auth") -> PlanMetadata:
    return prepare_project(project).plans.get(name).document.metadata


def read_state(project: Path) -> ProjectState:
    return prepare_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


def test_update_sets_status_explicit(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "active",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = UpdateResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.plan.document.metadata.status == "active"
    assert read_metadata(project).status == "active"


def test_update_sets_summary_and_tags(project: Path) -> None:
    seed_plan(project)
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--summary",
            "New summary",
            "--tag",
            "v2",
            "--tag",
            "backend",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    metadata = read_metadata(project)
    assert metadata.summary == "New summary"
    assert metadata.tags == ["v2", "backend"]


def test_update_clears_summary(project: Path) -> None:
    seed_plan(project)
    prepare_project(project).plans.update("auth", PlanUpdate(summary="Authored"))
    result = runner.invoke(
        app,
        ["plan", "update", "-p", "auth", "-P", str(project), "--summary", "", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert read_metadata(project).summary is None


def test_update_replaces_tags(project: Path) -> None:
    seed_plan(project)
    prepare_project(project).plans.update("auth", PlanUpdate(tags=["old"]))
    result = runner.invoke(
        app,
        ["plan", "update", "-p", "auth", "-P", str(project), "--tag", "new", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert read_metadata(project).tags == ["new"]


def test_update_uses_current_plan(project: Path) -> None:
    seed_plan(project, current=True)
    result = runner.invoke(
        app, ["plan", "update", "-P", str(project), "--status", "done", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_metadata(project).status == "done"


def test_update_non_interactive_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_plan(project, current=True)
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["plan", "update", "-P", str(project), "--status", "active"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Non-interactive mode requires an explicit plan" in error.error


def test_update_nothing_to_change(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app, ["plan", "update", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "Nothing to update" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_update_invalid_status_preserves_plan(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "nope",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Unknown status 'nope'" in error.error
    assert read_metadata(project).status == "draft"
    assert snapshot(project) == before


def test_update_missing_plan_preserves_state(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "absent",
            "-P",
            str(project),
            "--status",
            "active",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.project is not None
    assert "absent/plan.md" in error.error
    assert snapshot(project) == before


def test_update_invalid_name_preserves_target(project: Path) -> None:
    seed_plan(project)
    before = snapshot(project)
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "../bad",
            "-P",
            str(project),
            "--status",
            "active",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_update_only_changes_selected_plan(project: Path) -> None:
    seed_plan(project, "auth")
    seed_plan(project, "other")
    other_before = (project / ".machi/plans/other/plan.md").read_bytes()
    state_before = (project / ".machi/machinate.toml").read_bytes()
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "active",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert read_metadata(project, "auth").status == "active"
    assert read_metadata(project, "other").status == "draft"
    assert (project / ".machi/plans/other/plan.md").read_bytes() == other_before
    assert (project / ".machi/machinate.toml").read_bytes() == state_before


def test_update_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    result = runner.invoke(
        app, ["plan", "update", "-p", "auth", "--status", "active", "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_update_output(project: Path, format_name: str) -> None:
    seed_plan(project)
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "active",
            "--format",
            format_name,
        ],
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert UpdateResult.model_validate(json.loads(result.stdout)).plan.name == "auth"
    else:
        assert "Updated plan auth in example (active)" in result.stdout


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
def test_update_format_precedence(  # noqa: PLR0913
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
    args = ["plan", "update", "-p", "auth", "-P", str(project), "--status", "active"]
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
def test_update_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    seed_plan(project)
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(
        app, ["plan", "update", "-p", "auth", "-P", str(project), "--status", "active"]
    )
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_update_formatter_injection(project: Path) -> None:
    seed_plan(project)
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "active",
            "--format",
            "custom",
        ],
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], UpdateResult)
    result = runner.invoke(
        custom,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "nope",
            "--format",
            "custom",
        ],
    )
    assert result.exit_code == 1
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[1], ErrorResult)


def test_update_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_plan(project)
    application = prepare_project(project)
    plan = application.plans.get("auth")
    update = Mock(return_value=plan)
    monkeypatch.setattr(application.plans, "update", update)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "active",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    update.assert_called_once_with("auth", PlanUpdate(status="active"))
    assert UpdateResult.model_validate(json.loads(result.stdout)).plan.name == "auth"


def test_update_does_not_change_selection(project: Path) -> None:
    seed_plan(project, "auth", current=True)
    seed_plan(project, "other")
    result = runner.invoke(
        app,
        [
            "plan",
            "update",
            "-p",
            "other",
            "-P",
            str(project),
            "--status",
            "done",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert read_metadata(project, "other").status == "done"
    assert read_state(project).current_plan == "auth"


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_update_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["plan", "update", "-p", "auth", "--status", "active"]
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
    assert error.command == "plan update"
    assert "--unknown" in error.error
    factory.assert_not_called()
