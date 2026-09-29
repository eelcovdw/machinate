import json
from pathlib import Path
from typing import cast

import pytest
from harness import cli, read_state, seed

from machinate.cli.models import (
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
)
from machinate.cli.project_setup import prepare_project


@pytest.fixture
def auth_project(project: Path) -> Path:
    seed.plan(project, "auth")
    return project


TASK_INVOCATIONS = {
    "add": ["task", "add", "login"],
    "list": ["task", "list"],
    "show": ["task", "show", "login"],
    "info": ["task", "info", "login"],
    "update": ["task", "update", "login", "--status", "done"],
}


@pytest.mark.parametrize("command", list(TASK_INVOCATIONS))
def test_task_plan_resolution(auth_project: Path, command: str) -> None:
    """Every task subcommand shares select_plan, so resolution is tested once per command."""
    args = TASK_INVOCATIONS[command]
    unknown = cli.error([*args, "-p", "nope", "-P", str(auth_project), "--format", "json"])
    assert unknown.command == f"task {command}"

    unselected = cli.error([*args, "-P", str(auth_project), "--format", "json"])
    assert unselected.command == f"task {command}"


def test_task_add_explicit_plan(auth_project: Path) -> None:
    parsed = cli.json(
        TaskAddResult,
        ["task", "add", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.project.name == "example"
    assert parsed.project.directory == auth_project
    assert parsed.project.storage == auth_project / ".machi"
    assert parsed.plan == "auth"
    task = parsed.tasks[0]
    assert task.name == "login"
    assert task.path.as_posix() == "plans/auth/tasks/login.md"
    assert task.metadata.status == "todo"
    assert task.metadata.created_at.tzinfo is not None
    assert parsed.body == ""
    assert (auth_project / ".machi/plans/auth/tasks/login.md").is_file()
    assert read_state(auth_project).current_plan is None


def test_task_add_current_plan(auth_project: Path) -> None:
    prepare_project(auth_project).plans.set_current("auth")
    parsed = cli.json(
        TaskAddResult,
        ["task", "add", "login", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.plan == "auth"


def test_task_add_multiple(auth_project: Path) -> None:
    parsed = cli.json(
        TaskAddResult,
        [
            "task",
            "add",
            "login",
            "logout",
            "-p",
            "auth",
            "-P",
            str(auth_project),
            "--format",
            "json",
        ],
    )
    assert [task.name for task in parsed.tasks] == ["login", "logout"]


def test_task_add_batch_partial_success(auth_project: Path) -> None:
    """C2: an existing name must not abort the batch or swallow later names."""
    seed.task(auth_project, "auth", "existing")
    parsed = cli.json(
        TaskAddResult,
        [
            "task",
            "add",
            "new",
            "existing",
            "later",
            "../bad",
            "-p",
            "auth",
            "-P",
            str(auth_project),
            "--format",
            "json",
        ],
        expect=1,
    )
    assert parsed.command == "task add"
    assert [task.name for task in parsed.tasks] == ["new", "later"]
    assert [error.name for error in parsed.errors] == ["existing", "../bad"]
    assert (auth_project / ".machi/plans/auth/tasks/new.md").exists()
    assert (auth_project / ".machi/plans/auth/tasks/later.md").exists()
    assert (auth_project / ".machi/plans/auth/tasks/existing.md").exists()  # Not overwritten.


def test_task_add_batch_all_created_reports_no_errors(auth_project: Path) -> None:
    parsed = cli.json(
        TaskAddResult,
        ["task", "add", "one", "two", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.errors == []


def test_task_add_output(auth_project: Path) -> None:
    result = cli.run(["task", "add", "login", "-p", "auth", "-P", str(auth_project)])
    assert result.exit_code == 0, result.output
    assert "login" in result.output


def test_task_list_explicit_plan(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login", summary="Sign in")
    seed.task(auth_project, "auth", "logout")
    parsed = cli.json(
        TaskListResult,
        ["task", "list", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.project.name == "example"
    assert parsed.project.storage == auth_project / ".machi"
    assert parsed.plan == "auth"
    assert [task.name for task in parsed.tasks] == ["login", "logout"]
    assert parsed.tasks[0].path.as_posix() == "plans/auth/tasks/login.md"
    assert parsed.tasks[0].summary == "Sign in"
    assert parsed.tasks[0].metadata.status == "todo"
    assert read_state(auth_project).current_plan is None


def test_task_list_empty(auth_project: Path) -> None:
    parsed = cli.json(
        TaskListResult,
        ["task", "list", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.tasks == []


def test_task_list_output(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login", summary="Sign in")
    result = cli.run(["task", "list", "-p", "auth", "-P", str(auth_project)])
    assert result.exit_code == 0, result.output
    assert "login" in result.output


def test_task_show_explicit_plan(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login", summary="Sign in", body="Detailed notes")
    parsed = cli.json(
        TaskShowResult,
        ["task", "show", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.project.name == "example"
    assert parsed.project.storage == auth_project / ".machi"
    assert parsed.plan == "auth"
    assert parsed.task.name == "login"
    assert parsed.task.path.as_posix() == "plans/auth/tasks/login.md"
    assert parsed.task.summary == "Sign in"
    assert parsed.body == "Detailed notes"
    assert read_state(auth_project).current_plan is None


def test_task_show_output(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login", summary="Sign in", body="Detailed notes")
    result = cli.run(["task", "show", "login", "-p", "auth", "-P", str(auth_project)])
    assert result.exit_code == 0, result.output
    assert "login" in result.output


def test_task_info_explicit_plan(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login", summary="Sign in", body="Detailed notes")
    parsed = cli.json(
        TaskInfoResult,
        ["task", "info", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.project.name == "example"
    assert parsed.project.storage == auth_project / ".machi"
    assert parsed.plan == "auth"
    assert parsed.task.name == "login"
    assert parsed.task.path.as_posix() == "plans/auth/tasks/login.md"
    assert parsed.task.summary == "Sign in"
    assert read_state(auth_project).current_plan is None


def test_task_info_omits_body(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login", summary="Sign in", body="Detailed notes")
    result = cli.run(
        ["task", "info", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    payload = cast("dict[str, object]", json.loads(result.stdout)["task"])
    assert "document" not in payload
    assert "body" not in payload


def test_task_info_output(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login", summary="Sign in", body="Detailed notes")
    result = cli.run(["task", "info", "login", "-p", "auth", "-P", str(auth_project)])
    assert result.exit_code == 0, result.output
    assert "login" in result.output


def test_task_update_set_status_persists(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login")
    changed = cli.json(
        TaskUpdateResult,
        [
            "task",
            "update",
            "login",
            "--status",
            "in-progress",
            "-p",
            "auth",
            "-P",
            str(auth_project),
            "--format",
            "json",
        ],
    )
    assert changed.task.metadata.status == "in-progress"


def test_task_update_sets_summary_and_tags(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login")
    parsed = cli.json(
        TaskUpdateResult,
        [
            "task",
            "update",
            "login",
            "--summary",
            "Log in flow",
            "--tag",
            "v2",
            "--tag",
            "backend",
            "-p",
            "auth",
            "-P",
            str(auth_project),
            "--format",
            "json",
        ],
    )
    metadata = parsed.task.metadata
    assert parsed.task.summary == "Log in flow"
    assert metadata.tags == ["v2", "backend"]


def test_task_update_unknown_task(auth_project: Path) -> None:
    error = cli.error(
        [
            "task",
            "update",
            "missing",
            "--status",
            "done",
            "-p",
            "auth",
            "-P",
            str(auth_project),
            "--format",
            "json",
        ]
    )
    assert error.command == "task update"


def test_task_update_output(auth_project: Path) -> None:
    seed.task(auth_project, "auth", "login")
    result = cli.run(
        ["task", "update", "login", "--status", "done", "-p", "auth", "-P", str(auth_project)]
    )
    assert result.exit_code == 0, result.output
    assert "login" in result.output
