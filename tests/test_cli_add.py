import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import AddResult, ErrorResult, ListResult
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


def test_add_sets_summary_and_status(project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "plan",
            "add",
            "alpha",
            "-P",
            str(project),
            "--summary",
            "Does the thing",
            "--status",
            "active",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    metadata = AddResult.model_validate(json.loads(result.stdout)).plan.document.metadata
    assert metadata.summary == "Does the thing"
    assert metadata.status == "active"


def test_add_defaults_status_to_draft(project: Path) -> None:
    result = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    metadata = AddResult.model_validate(json.loads(result.stdout)).plan.document.metadata
    assert metadata.summary is None
    assert metadata.status == "draft"


def test_add_invalid_status_preserves_target(project: Path) -> None:
    before = snapshot(project)
    result = runner.invoke(
        app,
        ["plan", "add", "alpha", "-P", str(project), "--status", "nonsense", "--format", "json"],
    )
    assert result.exit_code == 1, result.output
    assert "Unknown status" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


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
