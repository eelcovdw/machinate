import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app
from machinate.cli.models import (
    AddResult,
    ContextAddResult,
    ErrorResult,
    TaskAddResult,
)
from machinate.storage import ProjectState, ProjectStateStore

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(root / ".machi/machinate.toml").write(ProjectState(project_name="example"))
    return root


def plan_add(project: Path, name: str, *tags: str) -> AddResult:
    args = ["plan", "add", name, "-P", str(project), "--format", "json"]
    for tag in tags:
        args.extend(["--tag", tag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return AddResult.model_validate(json.loads(result.stdout))


def task_add(project: Path, names: list[str], *tags: str) -> TaskAddResult:
    args = ["task", "add", *names, "-p", "alpha", "-P", str(project), "--format", "json"]
    for tag in tags:
        args.extend(["--tag", tag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return TaskAddResult.model_validate(json.loads(result.stdout))


def context_add(project: Path, names: list[str], *tags: str) -> ContextAddResult:
    args = ["context", "add", *names, "-p", "alpha", "-P", str(project), "--format", "json"]
    for tag in tags:
        args.extend(["--tag", tag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return ContextAddResult.model_validate(json.loads(result.stdout))


def test_plan_show_text_includes_tags(project: Path) -> None:
    plan_add(project, "alpha", "frontend", "v2")
    result = runner.invoke(
        app, ["plan", "show", "-p", "alpha", "-P", str(project), "--format", "text"]
    )
    assert result.exit_code == 0, result.output
    assert "Tags: frontend, v2" in result.stdout


def test_plan_info_text_includes_tags(project: Path) -> None:
    plan_add(project, "alpha", "frontend")
    result = runner.invoke(
        app, ["plan", "info", "-p", "alpha", "-P", str(project), "--format", "text"]
    )
    assert result.exit_code == 0, result.output
    assert "Tags: frontend" in result.stdout


def test_plan_update_tag_and_clear_tags_conflict(project: Path) -> None:
    plan_add(project, "alpha", "frontend")
    result = runner.invoke(
        app,
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
        ],
    )
    assert result.exit_code == 1, result.output
    assert "mutually exclusive" in ErrorResult.model_validate_json(result.stderr).error
    assert "frontend" in (project / ".machi/plans/alpha/plan.md").read_text()
