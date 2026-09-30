from pathlib import Path

from harness import cli, read_state

from machinate.cli.models import PlanAddResult


def test_add_explicit_project(project: Path) -> None:
    parsed = cli.json(
        PlanAddResult, ["plan", "add", "alpha", "-P", str(project), "--format", "json"]
    )
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.store_directory == project / ".machi"
    assert parsed.plan.name == "alpha"
    assert parsed.plan.path.as_posix() == "plans/alpha/plan.md"
    assert parsed.plan.metadata.status == "draft"
    assert parsed.plan.metadata.created_at.tzinfo is not None
    assert (project / ".machi/plans/alpha/plan.md").is_file()
    assert read_state(project).current_plan is None


def test_add_sets_summary_and_status(project: Path) -> None:
    parsed = cli.json(
        PlanAddResult,
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
    metadata = parsed.plan.metadata
    assert parsed.plan.summary == "Does the thing"
    assert metadata.status == "active"


def test_add_missing_project_directory(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    error = cli.error(
        ["plan", "add", "alpha", "-P", str(missing), "--format", "json"], code="project"
    )
    assert error.command == "plan add"
    assert not missing.exists()
