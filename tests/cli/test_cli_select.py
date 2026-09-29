from pathlib import Path

import pytest
from harness import cli, make_settings, read_state, seed

from machinate.cli.dependencies import Dependencies
from machinate.cli.models import SelectResult, ShowResult
from machinate.cli.project_setup import prepare_project


def set_current(project: Path, name: str) -> None:
    prepare_project(project).plans.set_current(name)


def test_select_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        SelectResult, ["plan", "select", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.state.current_plan == "auth"
    assert read_state(project).current_plan == "auth"


def test_select_works_in_automation(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        SelectResult,
        ["plan", "select", "auth", "-P", str(project), "--format", "json"],
        dependencies=Dependencies(settings=make_settings(automation=True)),
    )
    assert parsed.state.current_plan == "auth"
    assert read_state(project).current_plan == "auth"


def test_automation_mode_requires_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    set_current(project, "auth")
    error = cli.error(
        ["plan", "show", "-P", str(project)],
        dependencies=Dependencies(settings=make_settings(automation=True)),
    )
    assert error.command == "plan show"


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
        SelectResult, ["plan", "select", "auth", "-P", str(project), "--format", "json"]
    )
    assert selected.state.current_plan == "auth"
    shown = cli.json(ShowResult, ["plan", "show", "-P", str(project), "--format", "json"])
    assert shown.plan.name == "auth"


def test_unselect_parser_errors_use_json() -> None:
    error = cli.error(["plan", "unselect", "--unknown", "--format", "json"], expect=2)
    assert error.command == "plan unselect"
