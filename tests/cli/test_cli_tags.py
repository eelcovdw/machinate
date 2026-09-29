from pathlib import Path

from harness import cli, seed

from machinate.cli.models import PlanInfoResult, ShowResult
from machinate.cli.project_setup import prepare_project
from machinate.models.operations import PlanUpdate


def add_tags(project: Path, name: str, *tags: str) -> None:
    prepare_project(project).plans.update(name, PlanUpdate(tags=list(tags)))


def test_plan_show_includes_tags(project: Path) -> None:
    seed.plan(project, "alpha")
    add_tags(project, "alpha", "frontend", "v2")
    parsed = cli.json(
        ShowResult, ["plan", "show", "-p", "alpha", "-P", str(project), "--format", "json"]
    )
    assert parsed.plan.metadata.tags == ["frontend", "v2"]


def test_plan_info_includes_tags(project: Path) -> None:
    seed.plan(project, "alpha")
    add_tags(project, "alpha", "frontend")
    parsed = cli.json(
        PlanInfoResult,
        ["plan", "info", "-p", "alpha", "-P", str(project), "--format", "json"],
    )
    assert parsed.overview.plan.metadata.tags == ["frontend"]


def test_plan_update_tag_and_clear_tags_conflict(project: Path) -> None:
    seed.plan(project, "alpha")
    add_tags(project, "alpha", "frontend")
    error = cli.error(
        [
            "plan",
            "update",
            "-p",
            "alpha",
            "-P",
            str(project),
            "--tag",
            "backend",
            "--clear-tags",
            "--format",
            "json",
        ]
    )
    assert error.command == "plan update"
    assert prepare_project(project).plans.get("alpha").record.metadata.tags == ["frontend"]
