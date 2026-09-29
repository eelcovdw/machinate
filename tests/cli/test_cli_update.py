from pathlib import Path

import pytest
from harness import cli, read_state, seed, snapshot

from machinate.cli.models import UpdateResult
from machinate.cli.project_setup import prepare_project
from machinate.models.documents import PlanMetadata


def read_metadata(project: Path, name: str = "auth") -> PlanMetadata:
    return prepare_project(project).plans.get(name).document.metadata


def set_current(project: Path, name: str) -> None:
    prepare_project(project).plans.set_current(name)


def test_update_sets_status_explicit(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        UpdateResult,
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
    assert parsed.project.name == "example"
    assert parsed.plan.document.metadata.status == "active"
    assert read_metadata(project).status == "active"


def test_update_sets_summary_and_tags(project: Path) -> None:
    seed.plan(project, "auth")
    result = cli.run(
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
        ]
    )
    assert result.exit_code == 0, result.output
    metadata = read_metadata(project)
    assert metadata.summary == "New summary"
    assert metadata.tags == ["v2", "backend"]


def test_update_uses_current_plan(project: Path) -> None:
    seed.plan(project, "auth")
    set_current(project, "auth")
    result = cli.run(["plan", "update", "-P", str(project), "--status", "done", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_metadata(project).status == "done"


def test_update_missing_plan_preserves_state(
    project: Path,
) -> None:
    seed.plan(project, "auth")
    before = snapshot(project)
    error = cli.error(
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
        ]
    )
    assert error.project is not None
    assert snapshot(project) == before


def test_update_only_changes_selected_plan(project: Path) -> None:
    seed.plan(project, "auth")
    seed.plan(project, "other")
    other_before = (project / ".machi/plans/other/plan.md").read_bytes()
    state_before = (project / ".machi/machinate.toml").read_bytes()
    result = cli.run(
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
        ]
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
    error = cli.error(["plan", "update", "-p", "auth", "--status", "active", "--format", "json"])
    assert error.command == "plan update"


def test_update_text(project: Path) -> None:
    seed.plan(project, "auth")
    result = cli.run(
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
            "text",
        ]
    )
    assert result.exit_code == 0, result.output
    assert "auth" in result.stdout


def test_update_does_not_change_selection(
    project: Path,
) -> None:
    seed.plan(project, "auth")
    set_current(project, "auth")
    seed.plan(project, "other")
    result = cli.run(
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
        ]
    )
    assert result.exit_code == 0, result.output
    assert read_metadata(project, "other").status == "done"
    assert read_state(project).current_plan == "auth"
