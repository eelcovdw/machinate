import shutil
from pathlib import Path

from harness import cli, seed_plan

from machinate.cli.models import PlanShowResult
from machinate.cli.project_setup import open_project


def set_current(project: Path, name: str) -> None:
    open_project(project).plans.select_plan(name)


def test_show_explicit_plan(project: Path) -> None:
    seed_plan(project, "auth", body="# Auth\n\nDetails")
    parsed = cli.json(
        PlanShowResult, ["plan", "show", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.store_directory == project / ".machi"
    assert parsed.plan.name == "auth"
    assert parsed.plan.path.as_posix() == "plans/auth/plan.md"
    assert parsed.plan.metadata.status == "draft"
    assert parsed.plan.summary == "Details"
    assert parsed.body == "# Auth\n\nDetails"


def test_show_current_plan(project: Path) -> None:
    seed_plan(project, "auth")
    set_current(project, "auth")
    parsed = cli.json(PlanShowResult, ["plan", "show", "-P", str(project), "--format", "json"])
    assert parsed.plan.name == "auth"


def test_show_no_current_plan(project: Path) -> None:
    seed_plan(project, "auth")
    error = cli.error(["plan", "show", "-P", str(project), "--format", "json"], code="input")
    assert error.command == "plan show"
    assert error.project is not None


def test_show_deleted_current_plan(project: Path) -> None:
    seed_plan(project, "auth")
    set_current(project, "auth")
    shutil.rmtree(project / ".machi/plans/auth")
    error = cli.error(["plan", "show", "-P", str(project), "--format", "json"], code="input")
    assert error.command == "plan show"
