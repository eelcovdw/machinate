from pathlib import Path

from harness import cli, read_state, seed_plan

from machinate.cli.models import PlanSelectResult, PlanShowResult, PlanUnselectResult
from machinate.cli.project_setup import open_project


def set_current(project: Path, name: str) -> None:
    open_project(project).plans.select_plan(name)


def test_select_then_show(project: Path) -> None:
    seed_plan(project, "auth")
    selected = cli.json(
        PlanSelectResult, ["plan", "select", "auth", "-P", str(project), "--format", "json"]
    )
    assert selected.current_plan == "auth"
    shown = cli.json(PlanShowResult, ["plan", "show", "-P", str(project), "--format", "json"])
    assert shown.plan.name == "auth"


def test_unselect_success(project: Path) -> None:
    seed_plan(project, "auth")
    set_current(project, "auth")
    cli.json(PlanUnselectResult, ["plan", "unselect", "-P", str(project), "--format", "json"])
    assert read_state(project).current_plan is None
