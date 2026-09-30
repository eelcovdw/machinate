from pathlib import Path

import pytest
from harness import cli, read_state, seed_plan, seed_task

from machinate.cli.models import (
    PathResult,
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
)


@pytest.fixture
def auth_project(project: Path) -> Path:
    seed_plan(project, "auth")
    return project


def test_task_add_explicit_plan(auth_project: Path) -> None:
    parsed = cli.json(
        TaskAddResult,
        ["task", "add", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.project.directory == auth_project
    assert parsed.plan_name == "auth"
    task = parsed.batch.created[0]
    assert task.path.as_posix() == "plans/auth/tasks/login.md"
    assert task.metadata.status == "todo"
    assert (auth_project / ".machi/plans/auth/tasks/login.md").is_file()
    assert read_state(auth_project).current_plan is None


def test_task_add_batch_partial_success(auth_project: Path) -> None:
    seed_task(auth_project, "auth", "existing")
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
    assert [task.name for task in parsed.batch.created] == ["new", "later"]
    assert [error.name for error in parsed.batch.failures] == ["existing", "../bad"]
    assert (auth_project / ".machi/plans/auth/tasks/existing.md").exists()  # Not overwritten.


def test_task_list_explicit_plan(auth_project: Path) -> None:
    seed_task(auth_project, "auth", "login", summary="Sign in")
    seed_task(auth_project, "auth", "logout")
    parsed = cli.json(
        TaskListResult,
        ["task", "list", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.plan_name == "auth"
    assert [task.name for task in parsed.tasks] == ["login", "logout"]
    assert parsed.tasks[0].summary == "Sign in"
    assert read_state(auth_project).current_plan is None


def test_task_show_explicit_plan(auth_project: Path) -> None:
    seed_task(auth_project, "auth", "login", summary="Sign in", body="Detailed notes")
    parsed = cli.json(
        TaskShowResult,
        ["task", "show", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.task.path.as_posix() == "plans/auth/tasks/login.md"
    assert parsed.task.summary == "Sign in"
    assert parsed.body == "Detailed notes"


def test_task_info_explicit_plan(auth_project: Path) -> None:
    seed_task(auth_project, "auth", "login", summary="Sign in", body="Detailed notes")
    parsed = cli.json(
        TaskInfoResult,
        ["task", "info", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.task.name == "login"
    assert parsed.task.summary == "Sign in"


def test_task_update_set_status_persists(auth_project: Path) -> None:
    seed_task(auth_project, "auth", "login")
    changed = cli.json(
        TaskUpdateResult,
        [
            "task",
            "update",
            "login",
            "--status",
            "in-progress",
            "--tag",
            "v2",
            "-p",
            "auth",
            "-P",
            str(auth_project),
            "--format",
            "json",
        ],
    )
    assert changed.task.metadata.status == "in-progress"
    assert changed.task.metadata.tags == ["v2"]


def test_task_path_explicit_plan(auth_project: Path) -> None:
    seed_task(auth_project, "auth", "login")
    parsed = cli.json(
        PathResult,
        ["task", "path", "login", "-p", "auth", "-P", str(auth_project), "--format", "json"],
    )
    assert parsed.absolute_path.as_posix().endswith("plans/auth/tasks/login.md")
