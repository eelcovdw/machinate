import json
from pathlib import Path

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app
from machinate.cli.models import (
    AddResult,
    ContextAddResult,
    ContextListResult,
    ErrorResult,
    ListResult,
    TaskAddResult,
    TaskListResult,
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
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example")
    )
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


def test_plan_add_tags(project: Path) -> None:
    parsed = plan_add(project, "alpha", "frontend", "v2")
    assert parsed.plan.document.metadata.tags == ["frontend", "v2"]
    assert "frontend" in (project / ".machi/plans/alpha/plan.md").read_text()


def test_plan_add_dedupes_tags_case_insensitively(project: Path) -> None:
    parsed = plan_add(project, "alpha", "frontend", "Frontend", "  v2  ")
    assert parsed.plan.document.metadata.tags == ["frontend", "v2"]


@pytest.mark.parametrize("invalid", ["", "   ", "bad\x01"])
def test_plan_add_invalid_tag_preserves_target(project: Path, invalid: str) -> None:
    result = runner.invoke(
        app, ["plan", "add", "alpha", "-P", str(project), "--format", "json", "--tag", invalid]
    )
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty tag" in ErrorResult.model_validate_json(result.stderr).error
    assert not (project / ".machi/plans/alpha").exists()


def test_plan_add_invalid_tag_automation_json(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["plan", "add", "alpha", "-P", str(project), "--tag", ""])
    assert result.exit_code == 1
    assert "Expected a nonempty tag" in ErrorResult.model_validate_json(result.stderr).error


def test_plan_list_filters_by_tag(project: Path) -> None:
    plan_add(project, "alpha", "frontend")
    plan_add(project, "beta", "backend", "v2")
    plan_add(project, "gamma")
    result = runner.invoke(
        app, ["plan", "list", "-P", str(project), "--format", "json", "--tag", "frontend"]
    )
    assert result.exit_code == 0, result.output
    assert [plan.name for plan in ListResult.model_validate(json.loads(result.stdout)).plans] == [
        "alpha"
    ]


def test_plan_list_tag_any_match(project: Path) -> None:
    plan_add(project, "alpha", "frontend")
    plan_add(project, "beta", "backend")
    plan_add(project, "gamma")
    result = runner.invoke(
        app,
        [
            "plan",
            "list",
            "-P",
            str(project),
            "--format",
            "json",
            "--tag",
            "frontend",
            "--tag",
            "backend",
        ],
    )
    assert result.exit_code == 0, result.output
    assert [plan.name for plan in ListResult.model_validate(json.loads(result.stdout)).plans] == [
        "alpha",
        "beta",
    ]


def test_plan_list_tag_matches_case_insensitively(project: Path) -> None:
    plan_add(project, "alpha", "Frontend")
    result = runner.invoke(
        app, ["plan", "list", "-P", str(project), "--format", "json", "--tag", "frontend"]
    )
    assert result.exit_code == 0, result.output
    assert [plan.name for plan in ListResult.model_validate(json.loads(result.stdout)).plans] == [
        "alpha"
    ]


def test_plan_list_search_matches_tag(project: Path) -> None:
    plan_add(project, "alpha", "frontend")
    plan_add(project, "beta", "backend")
    result = runner.invoke(
        app, ["plan", "list", "-P", str(project), "--format", "json", "--search", "frontend"]
    )
    assert result.exit_code == 0, result.output
    assert [plan.name for plan in ListResult.model_validate(json.loads(result.stdout)).plans] == [
        "alpha"
    ]


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


def test_plan_list_text_includes_tags(project: Path) -> None:
    plan_add(project, "alpha", "frontend")
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "text"])
    assert result.exit_code == 0, result.output
    assert "draft (1)" in result.stdout
    assert "alpha" in result.stdout
    assert "frontend" in result.stdout


def test_task_add_and_list_tags(project: Path) -> None:
    plan_add(project, "alpha")
    parsed = task_add(project, ["t1", "t2"], "cli")
    assert [task.document.metadata.tags for task in parsed.tasks] == [["cli"], ["cli"]]
    result = runner.invoke(
        app, ["task", "list", "-p", "alpha", "-P", str(project), "--format", "json", "--tag", "cli"]
    )
    assert result.exit_code == 0, result.output
    assert [
        task.name for task in TaskListResult.model_validate(json.loads(result.stdout)).tasks
    ] == ["t1", "t2"]
    empty = runner.invoke(
        app,
        ["task", "list", "-p", "alpha", "-P", str(project), "--format", "json", "--tag", "nope"],
    )
    assert empty.exit_code == 0, empty.output
    assert TaskListResult.model_validate(json.loads(empty.stdout)).tasks == []


def test_task_show_and_info_text_include_tags(project: Path) -> None:
    plan_add(project, "alpha")
    task_add(project, ["t1"], "cli")
    shown = runner.invoke(
        app, ["task", "show", "t1", "-p", "alpha", "-P", str(project), "--format", "text"]
    )
    assert shown.exit_code == 0, shown.output
    assert "Tags: cli" in shown.stdout
    info = runner.invoke(
        app, ["task", "info", "t1", "-p", "alpha", "-P", str(project), "--format", "text"]
    )
    assert info.exit_code == 0, info.output
    assert "Tags: cli" in info.stdout


def test_context_add_and_list_tags(project: Path) -> None:
    plan_add(project, "alpha")
    parsed = context_add(project, ["spec"], "docs")
    assert parsed.contexts[0].document.metadata.tags == ["docs"]
    result = runner.invoke(
        app,
        ["context", "list", "-p", "alpha", "-P", str(project), "--format", "json", "--tag", "docs"],
    )
    assert result.exit_code == 0, result.output
    assert [
        context.name
        for context in ContextListResult.model_validate(json.loads(result.stdout)).contexts
    ] == ["spec"]


def test_context_show_and_info_text_include_tags(project: Path) -> None:
    plan_add(project, "alpha")
    context_add(project, ["spec"], "docs")
    shown = runner.invoke(
        app, ["context", "show", "spec", "-p", "alpha", "-P", str(project), "--format", "text"]
    )
    assert shown.exit_code == 0, shown.output
    assert "Tags: docs" in shown.stdout
    info = runner.invoke(
        app, ["context", "info", "spec", "-p", "alpha", "-P", str(project), "--format", "text"]
    )
    assert info.exit_code == 0, info.output
    assert "Tags: docs" in info.stdout


def test_plan_update_clear_tags(project: Path) -> None:
    plan_add(project, "alpha", "frontend", "v2")
    result = runner.invoke(
        app,
        ["plan", "update", "-p", "alpha", "-P", str(project), "--clear-tags", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    text = (project / ".machi/plans/alpha/plan.md").read_text()
    assert "tags: []" in text
    assert "frontend" not in text


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


def test_task_update_clear_tags(project: Path) -> None:
    plan_add(project, "alpha")
    task_add(project, ["t1"], "cli")
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "t1",
            "-p",
            "alpha",
            "-P",
            str(project),
            "--clear-tags",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (project / ".machi/plans/alpha/tasks/t1.md").read_text()
    assert "tags: []" in text
    assert "cli" not in text


def test_task_update_tag_and_clear_tags_conflict(project: Path) -> None:
    plan_add(project, "alpha")
    task_add(project, ["t1"], "cli")
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "t1",
            "-p",
            "alpha",
            "-P",
            str(project),
            "--tag",
            "x",
            "--clear-tags",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "mutually exclusive" in ErrorResult.model_validate_json(result.stderr).error
    assert "cli" in (project / ".machi/plans/alpha/tasks/t1.md").read_text()


def test_context_update_clear_tags(project: Path) -> None:
    plan_add(project, "alpha")
    context_add(project, ["spec"], "docs")
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
            "-p",
            "alpha",
            "-P",
            str(project),
            "--clear-tags",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (project / ".machi/plans/alpha/context/spec.md").read_text()
    assert "tags: []" in text
    assert "docs" not in text


def test_context_update_tag_and_clear_tags_conflict(project: Path) -> None:
    plan_add(project, "alpha")
    context_add(project, ["spec"], "docs")
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
            "-p",
            "alpha",
            "-P",
            str(project),
            "--tag",
            "x",
            "--clear-tags",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "mutually exclusive" in ErrorResult.model_validate_json(result.stderr).error
    assert "docs" in (project / ".machi/plans/alpha/context/spec.md").read_text()
