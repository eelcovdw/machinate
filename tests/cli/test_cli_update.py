from pathlib import Path

from harness import cli, read_state, seed_plan, snapshot

from machinate.cli.models import PlanUpdateResult
from machinate.cli.project_setup import open_project
from machinate.models.documents import PlanMetadata, PlanStatus
from machinate.models.operations import StatusUpdate


def read_metadata(project: Path, name: str = "auth") -> PlanMetadata:
    return open_project(project).plans.get(name).record.metadata


def set_current(project: Path, name: str) -> None:
    open_project(project).plans.select_plan(name)


def add_tags(project: Path, name: str, *tags: str) -> None:
    open_project(project).plans.update(name, StatusUpdate[PlanStatus](tags=list(tags)))


def test_update_status_summary_and_tags(project: Path) -> None:
    seed_plan(project, "auth")
    parsed = cli.json(
        PlanUpdateResult,
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "active",
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
    assert parsed.plan.metadata.status == "active"
    metadata = read_metadata(project)
    assert metadata.status == "active"
    assert metadata.summary == "New summary"
    assert metadata.tags == ["v2", "backend"]


def test_update_clear_tags_success(project: Path) -> None:
    seed_plan(project, "auth")
    add_tags(project, "auth", "frontend", "v2")
    cli.json(
        PlanUpdateResult,
        ["plan", "update", "-p", "auth", "-P", str(project), "--clear-tags", "--format", "json"],
    )
    assert read_metadata(project).tags == []


def test_update_tag_and_clear_tags_conflict(project: Path) -> None:
    seed_plan(project, "auth")
    add_tags(project, "auth", "frontend")
    error = cli.error(
        [
            "plan",
            "update",
            "-p",
            "auth",
            "-P",
            str(project),
            "--tag",
            "backend",
            "--clear-tags",
            "--format",
            "json",
        ],
        code="input",
    )
    assert error.command == "plan update"
    assert read_metadata(project).tags == ["frontend"]


def test_update_missing_plan_preserves_state(project: Path) -> None:
    seed_plan(project, "auth")
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
        ],
        code="not_found",
    )
    assert error.project is not None
    assert snapshot(project) == before


def test_update_does_not_change_selection(project: Path) -> None:
    seed_plan(project, "auth")
    set_current(project, "auth")
    seed_plan(project, "other")
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
    assert read_state(project).current_plan == "auth"
