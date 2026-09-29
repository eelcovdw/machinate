from pathlib import Path

import pytest
from harness import cli, make_settings, seed

from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ShowResult
from machinate.cli.project_setup import prepare_project


def set_current(project: Path, name: str) -> None:
    prepare_project(project).plans.set_current(name)


def test_show_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth", body="# Auth\n\nDetails")
    parsed = cli.json(
        ShowResult, ["plan", "show", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan.name == "auth"
    assert parsed.plan.path.as_posix() == "plans/auth/plan.md"
    assert parsed.plan.document.metadata.status == "draft"
    assert parsed.plan.document.get_or_derive_summary() == "Details"
    assert parsed.plan.document.body == "# Auth\n\nDetails"


def test_show_current_plan(project: Path) -> None:
    seed.plan(project, "auth")
    set_current(project, "auth")
    parsed = cli.json(ShowResult, ["plan", "show", "-P", str(project), "--format", "json"])
    assert parsed.plan.name == "auth"


def test_show_current_directory(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed.plan(project, "auth")
    monkeypatch.chdir(project)
    parsed = cli.json(ShowResult, ["plan", "show", "-p", "auth", "--format", "json"])
    assert parsed.project.directory == project


def test_show_discovers_upward(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed.plan(project, "auth")
    child = project / "nested"
    child.mkdir()
    monkeypatch.chdir(child)
    parsed = cli.json(ShowResult, ["plan", "show", "-p", "auth", "--format", "json"])
    assert parsed.project.directory == project


def test_show_no_current_plan(project: Path) -> None:
    seed.plan(project, "auth")
    error = cli.error(["plan", "show", "-P", str(project), "--format", "json"])
    assert error.command == "plan show"
    assert error.project is not None


def test_show_automation_requires_plan(project: Path) -> None:
    seed.plan(project, "auth")
    set_current(project, "auth")
    error = cli.error(
        ["plan", "show", "-P", str(project)],
        dependencies=Dependencies(settings=make_settings(automation=True)),
    )
    assert error.command == "plan show"


def test_show_uninitialized_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "uninitialized"
    target.mkdir()
    monkeypatch.chdir(target)
    error = cli.error(["plan", "show", "-p", "auth", "--format", "json"])
    assert error.command == "plan show"


def test_show_text(project: Path) -> None:
    seed.plan(project, "auth")
    result = cli.run(["plan", "show", "-p", "auth", "-P", str(project), "--format", "text"])
    assert result.exit_code == 0, result.output
    assert "auth" in result.stdout
