from pathlib import Path

import pytest
from harness import cli, read_state, seed

from machinate.cli.models import AddResult
from machinate.cli.project_setup import prepare_project


def test_add_explicit_project(project: Path) -> None:
    parsed = cli.json(AddResult, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
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
    parsed = cli.json(AddResult, ["plan", "add", "alpha", "--format", "json"])
    assert parsed.project.directory == project


def test_add_sets_summary_and_status(project: Path) -> None:
    parsed = cli.json(
        AddResult,
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
    metadata = parsed.plan.document.metadata
    assert metadata.summary == "Does the thing"
    assert metadata.status == "active"


def test_add_never_changes_selection(project: Path) -> None:
    seed.plan(project, "existing")
    prepare_project(project).plans.set_current("existing")
    cli.json(AddResult, ["plan", "add", "alpha", "-P", str(project), "--format", "json"])
    assert read_state(project).current_plan == "existing"


def test_add_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    error = cli.error(["plan", "add", "alpha", "--format", "json"])
    assert error.command == "plan add"


def test_add_missing_project_directory(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    error = cli.error(["plan", "add", "alpha", "-P", str(missing), "--format", "json"])
    assert error.command == "plan add"
    assert not missing.exists()


def test_add_output(project: Path) -> None:
    result = cli.run(["plan", "add", "alpha", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "alpha" in result.output
