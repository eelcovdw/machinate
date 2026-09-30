from pathlib import Path

import pytest
from harness import cli, read_state, seed

from machinate.cli.models import PlanSelectResult, PlanShowResult
from machinate.cli.project_setup import open_project


def set_current(project: Path, name: str) -> None:
    open_project(project).plans.select_plan(name)


def test_select_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        PlanSelectResult, ["plan", "select", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.current_plan == "auth"
    assert read_state(project).current_plan == "auth"


def test_select_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    error = cli.error(["plan", "select", "auth", "--format", "json"])
    assert error.command == "plan select"


def test_select_text(project: Path) -> None:
    seed.plan(project, "auth")
    result = cli.run(["plan", "select", "auth", "-P", str(project), "--format", "text"])
    assert result.exit_code == 0, result.output
    assert "auth" in result.stdout


def test_select_then_show(project: Path) -> None:
    seed.plan(project, "auth")
    selected = cli.json(
        PlanSelectResult, ["plan", "select", "auth", "-P", str(project), "--format", "json"]
    )
    assert selected.current_plan == "auth"
    shown = cli.json(PlanShowResult, ["plan", "show", "-P", str(project), "--format", "json"])
    assert shown.plan.name == "auth"


def test_unselect_parser_errors_use_json() -> None:
    error = cli.error(["plan", "unselect", "--unknown", "--format", "json"], expect=2)
    assert error.command == "plan unselect"
