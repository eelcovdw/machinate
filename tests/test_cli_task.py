import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import (
    ErrorResult,
    ListResult,
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
)
from machinate.cli.project_setup import prepare_project
from machinate.models.task import TaskUpdate
from machinate.storage import PlanMetadata, ProjectState, ProjectStateStore, TaskMetadata
from machinate.storage.queries import TaskQuery

runner = CliRunner()

_DEFAULT_CREATED = datetime(2026, 1, 1, tzinfo=UTC)


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
    prepare_project(root).plans.create(
        "auth", PlanMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )
    return root


def read_state(project: Path) -> ProjectState:
    return prepare_project(project).plans.project_state_store.read()


def snapshot(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}


TASK_INVOCATIONS = {
    "add": ["task", "add", "login"],
    "list": ["task", "list"],
    "show": ["task", "show", "login"],
    "info": ["task", "info", "login"],
    "update": ["task", "update", "login", "--status", "done"],
}


@pytest.mark.parametrize("args", list(TASK_INVOCATIONS.values()), ids=list(TASK_INVOCATIONS))
def test_task_plan_resolution(
    project: Path, args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every task subcommand shares select_plan, so resolution is tested once per command."""
    unknown = runner.invoke(app, [*args, "-p", "nope", "-P", str(project), "--format", "json"])
    assert unknown.exit_code == 1, unknown.output
    assert "nope" in ErrorResult.model_validate_json(unknown.stderr).error

    unselected = runner.invoke(app, [*args, "-P", str(project), "--format", "json"])
    assert unselected.exit_code == 1, unselected.output
    assert "No current plan is selected" in ErrorResult.model_validate_json(unselected.stderr).error

    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    automated = runner.invoke(app, [*args, "-P", str(project)])
    assert automated.exit_code == 1, automated.output
    assert (
        "Automation mode requires an explicit plan"
        in ErrorResult.model_validate_json(automated.stderr).error
    )


def test_task_add_explicit_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = TaskAddResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan == "auth"
    task = parsed.tasks[0]
    assert task.name == "login"
    assert task.path.as_posix() == "plans/auth/tasks/login.md"
    assert task.document.metadata.status == "todo"
    assert task.document.metadata.created.tzinfo is not None
    assert task.document.body == ""
    assert (project / ".machi/plans/auth/tasks/login.md").is_file()
    assert read_state(project).current_plan is None


def test_task_add_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["task", "add", "login", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert TaskAddResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_task_add_multiple(project: Path) -> None:
    result = runner.invoke(
        app,
        ["task", "add", "login", "logout", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    names = [task.name for task in TaskAddResult.model_validate(json.loads(result.stdout)).tasks]
    assert names == ["login", "logout"]


def test_task_add_batch_partial_success(project: Path) -> None:
    """C2: an existing name must not abort the batch or swallow later names."""
    prepare_project(project).tasks.create(
        "auth", "existing", TaskMetadata(created=_DEFAULT_CREATED)
    )
    result = runner.invoke(
        app,
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
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    parsed = TaskAddResult.model_validate(json.loads(result.stdout))
    assert [task.name for task in parsed.tasks] == ["new", "later"]
    assert [error.name for error in parsed.errors] == ["existing", "../bad"]
    assert "Already exists" in parsed.errors[0].error
    assert "Expected a nonempty name" in parsed.errors[1].error
    assert (project / ".machi/plans/auth/tasks/new.md").exists()
    assert (project / ".machi/plans/auth/tasks/later.md").exists()
    assert (project / ".machi/plans/auth/tasks/existing.md").exists()  # Not overwritten.


def test_task_add_batch_partial_success_text_reports_errors(project: Path) -> None:
    """Text output must surface rejected names, not only exit non-zero."""
    prepare_project(project).tasks.create(
        "auth", "existing", TaskMetadata(created=_DEFAULT_CREATED)
    )
    result = runner.invoke(
        app,
        [
            "task",
            "add",
            "new",
            "existing",
            "../bad",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "text",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "Created 1 task(s)" in result.stdout
    assert "Not created:" in result.stdout
    assert "existing" in result.stdout
    assert "Already exists" in result.stdout
    assert "../bad" in result.stdout
    assert "Expected a nonempty name" in result.stdout
    assert (project / ".machi/plans/auth/tasks/new.md").exists()


def test_task_add_batch_all_created_reports_no_errors(project: Path) -> None:
    result = runner.invoke(
        app,
        ["task", "add", "one", "two", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    parsed = TaskAddResult.model_validate(json.loads(result.stdout))
    assert parsed.errors == []


def test_task_add_duplicate_preserves_existing(project: Path) -> None:
    """A duplicate is now a partial-failure result, not a global error."""
    first = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert first.exit_code == 0, first.output
    before = snapshot(project)
    duplicate = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert duplicate.exit_code == 1, duplicate.output
    parsed = TaskAddResult.model_validate(json.loads(duplicate.stdout))
    assert parsed.tasks == []
    assert [error.name for error in parsed.errors] == ["login"]
    assert "Already exists" in parsed.errors[0].error
    assert snapshot(project) == before


@pytest.mark.parametrize("invalid", ["../bad", "a\\b", "a:b", "", ".", "..", "/leading", "trail/"])
def test_task_add_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    before = snapshot(project)
    result = runner.invoke(
        app, ["task", "add", invalid, "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    parsed = TaskAddResult.model_validate(json.loads(result.stdout))
    assert parsed.tasks == []
    assert [error.name for error in parsed.errors] == [invalid]
    assert snapshot(project) == before


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_task_add_output(project: Path, format_name: str) -> None:
    result = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        parsed = TaskAddResult.model_validate(json.loads(result.stdout))
        assert parsed.tasks[0].name == "login"
    else:
        assert "Created 1 task(s) in example/auth" in result.stdout
        assert str(project / ".machi/plans/auth/tasks/login.md") in result.stdout


def test_task_add_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed = application.tasks.create(
        "auth", "seed", TaskMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )
    create_batch = Mock(return_value=([seed], []))
    monkeypatch.setattr(application.tasks, "create_batch", create_batch)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    create_batch.assert_called_once()
    call_plan, call_names, call_metadata = cast(
        "tuple[str, list[str], TaskMetadata]", create_batch.call_args.args
    )
    assert call_plan == "auth"
    assert call_names == ["login"]
    assert call_metadata.status == "todo"
    assert call_metadata.created.tzinfo is not None
    assert TaskAddResult.model_validate(json.loads(result.stdout)).tasks[0].name == "seed"


def test_task_add_stamps_aware_utc(project: Path) -> None:
    before = datetime.now(UTC)
    result = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    after = datetime.now(UTC)
    assert result.exit_code == 0, result.output
    created = (
        TaskAddResult.model_validate(json.loads(result.stdout)).tasks[0].document.metadata.created
    )
    assert created.tzinfo is not None
    assert before <= created <= after


def test_task_add_then_show_and_list(project: Path) -> None:
    added = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert added.exit_code == 0, added.output
    shown = runner.invoke(
        app, ["plan", "show", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert shown.exit_code == 0, shown.output
    listed = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
    assert [plan.name for plan in ListResult.model_validate(json.loads(listed.stdout)).plans] == [
        "auth"
    ]


def seed_task(project: Path, name: str, summary: str | None = None, body: str = "") -> None:
    if summary is not None:
        body = summary if not body else f"{summary}\n\n{body}"
    prepare_project(project).tasks.create(
        "auth", name, TaskMetadata(created=datetime(2026, 1, 1, tzinfo=UTC)), body=body
    )


def test_task_list_explicit_plan(project: Path) -> None:
    seed_task(project, "login", summary="Sign in")
    seed_task(project, "logout")
    result = runner.invoke(
        app, ["task", "list", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = TaskListResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan == "auth"
    assert [task.name for task in parsed.tasks] == ["login", "logout"]
    assert parsed.tasks[0].path.as_posix() == "plans/auth/tasks/login.md"
    assert parsed.tasks[0].summary == "Sign in"
    assert parsed.tasks[0].metadata.status == "todo"
    assert read_state(project).current_plan is None


def test_task_list_empty(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "list", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert TaskListResult.model_validate(json.loads(result.stdout)).tasks == []


def test_task_list_status_search_and_body(project: Path) -> None:
    seed_task(project, "alpha", summary="first")
    seed_task(project, "beta", summary="second")
    seed_task(project, "gamma", body="gamma notes\n\nsecret needle")
    prepare_project(project).tasks.set_status("auth", "beta", "done")

    by_status = runner.invoke(
        app,
        [
            "task",
            "list",
            "-p",
            "auth",
            "-P",
            str(project),
            "--status",
            "done",
            "--format",
            "json",
        ],
    )
    assert [
        task.name for task in TaskListResult.model_validate(json.loads(by_status.stdout)).tasks
    ] == ["beta"]

    by_search = runner.invoke(
        app,
        [
            "task",
            "list",
            "-p",
            "auth",
            "-P",
            str(project),
            "--search",
            "second",
            "--format",
            "json",
        ],
    )
    assert [
        task.name for task in TaskListResult.model_validate(json.loads(by_search.stdout)).tasks
    ] == ["beta"]

    without_body = runner.invoke(
        app,
        [
            "task",
            "list",
            "-p",
            "auth",
            "-P",
            str(project),
            "--search",
            "needle",
            "--format",
            "json",
        ],
    )
    assert TaskListResult.model_validate(json.loads(without_body.stdout)).tasks == []

    with_body = runner.invoke(
        app,
        [
            "task",
            "list",
            "-p",
            "auth",
            "-P",
            str(project),
            "--search",
            "needle",
            "--search-body",
            "--format",
            "json",
        ],
    )
    assert [
        task.name for task in TaskListResult.model_validate(json.loads(with_body.stdout)).tasks
    ] == ["gamma"]


def test_task_list_sort_and_limit(project: Path) -> None:
    seed_task(project, "alpha")
    seed_task(project, "beta")

    limited = runner.invoke(
        app,
        ["task", "list", "-p", "auth", "-P", str(project), "--limit", "1", "--format", "json"],
    )
    assert [
        task.name for task in TaskListResult.model_validate(json.loads(limited.stdout)).tasks
    ] == ["alpha"]

    descending = runner.invoke(
        app,
        [
            "task",
            "list",
            "-p",
            "auth",
            "-P",
            str(project),
            "--descending",
            "--format",
            "json",
        ],
    )
    assert [
        task.name for task in TaskListResult.model_validate(json.loads(descending.stdout)).tasks
    ] == ["beta", "alpha"]


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_task_list_output(project: Path, format_name: str) -> None:
    seed_task(project, "login", summary="Sign in")
    result = runner.invoke(
        app, ["task", "list", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert TaskListResult.model_validate(json.loads(result.stdout)).tasks[0].name == "login"
    else:
        assert "example / auth" in result.stdout
        assert "Sign in" in result.stdout


def test_task_list_empty_text(project: Path) -> None:
    result = runner.invoke(app, ["task", "list", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "No tasks found." in result.stdout


def test_task_list_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed_task(project, "seed")
    records = application.tasks.list("auth")
    listing = Mock(return_value=records)
    monkeypatch.setattr(application.tasks, "list", listing)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["task", "list", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    listing.assert_called_once()
    call_plan, call_query = cast("tuple[str, TaskQuery]", listing.call_args.args)
    assert call_plan == "auth"
    assert isinstance(call_query, TaskQuery)
    assert call_query.sort == "name"
    assert TaskListResult.model_validate(json.loads(result.stdout)).tasks[0].name == "seed"


def test_task_show_explicit_plan(project: Path) -> None:
    seed_task(project, "login", summary="Sign in", body="Detailed notes")
    result = runner.invoke(
        app, ["task", "show", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = TaskShowResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan == "auth"
    assert parsed.task.name == "login"
    assert parsed.task.path.as_posix() == "plans/auth/tasks/login.md"
    assert parsed.task.document.get_or_derive_summary() == "Sign in"
    assert parsed.task.document.body == "Sign in\n\nDetailed notes"
    assert read_state(project).current_plan is None


def test_task_show_missing_task_preserves_project(project: Path) -> None:
    seed_task(project, "login")
    before = snapshot(project)
    result = runner.invoke(
        app, ["task", "show", "missing", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task show"
    assert "missing" in error.error
    assert snapshot(project) == before


@pytest.mark.parametrize("invalid", ["../bad", "a\\b", "a:b", "", ".", "..", "/leading", "trail/"])
def test_task_show_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    seed_task(project, "login")
    before = snapshot(project)
    result = runner.invoke(
        app, ["task", "show", invalid, "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task show"
    assert snapshot(project) == before


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_task_show_output(project: Path, format_name: str) -> None:
    seed_task(project, "login", summary="Sign in", body="Detailed notes")
    result = runner.invoke(
        app, ["task", "show", "login", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert TaskShowResult.model_validate(json.loads(result.stdout)).task.name == "login"
    else:
        assert "Task login (todo)" in result.stdout
        assert "example / auth" in result.stdout
        assert "Sign in" in result.stdout
        assert "Detailed notes" in result.stdout


def test_task_show_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed_task(project, "seed")
    record = application.tasks.get("auth", "seed")
    get = Mock(return_value=record)
    monkeypatch.setattr(application.tasks, "get", get)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["task", "show", "seed", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    get.assert_called_once_with("auth", "seed")
    assert TaskShowResult.model_validate(json.loads(result.stdout)).task.name == "seed"


def test_task_info_explicit_plan(project: Path) -> None:
    seed_task(project, "login", summary="Sign in", body="Detailed notes")
    result = runner.invoke(
        app, ["task", "info", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = TaskInfoResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan == "auth"
    assert parsed.task.name == "login"
    assert parsed.task.path.as_posix() == "plans/auth/tasks/login.md"
    assert parsed.task.summary == "Sign in"
    assert read_state(project).current_plan is None


def test_task_info_omits_body(project: Path) -> None:
    seed_task(project, "login", summary="Sign in", body="Detailed notes")
    result = runner.invoke(
        app, ["task", "info", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    payload = cast("dict[str, object]", json.loads(result.stdout)["task"])
    assert "document" not in payload
    assert "body" not in payload


def test_task_info_missing_task_preserves_project(project: Path) -> None:
    seed_task(project, "login")
    before = snapshot(project)
    result = runner.invoke(
        app, ["task", "info", "missing", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task info"
    assert "missing" in error.error
    assert snapshot(project) == before


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_task_info_output(project: Path, format_name: str) -> None:
    seed_task(project, "login", summary="Sign in", body="Detailed notes")
    result = runner.invoke(
        app, ["task", "info", "login", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert TaskInfoResult.model_validate(json.loads(result.stdout)).task.name == "login"
    else:
        assert "Task login (todo)" in result.stdout
        assert "example / auth" in result.stdout
        assert "Summary: Sign in" in result.stdout
        assert "Detailed notes" not in result.stdout


def test_task_update_set_status_persists(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "login",
            "--status",
            "in-progress",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    changed = TaskUpdateResult.model_validate(json.loads(result.stdout))
    assert changed.task.document.metadata.status == "in-progress"


def test_task_update_sets_summary_and_tags(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app,
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
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    metadata = TaskUpdateResult.model_validate(json.loads(result.stdout)).task.document.metadata
    assert metadata.summary == "Log in flow"
    assert metadata.tags == ["v2", "backend"]


def test_task_update_clears_summary(project: Path) -> None:
    seed_task(project, "login")
    prepare_project(project).tasks.update("auth", "login", TaskUpdate(summary="Authored"))
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "login",
            "--summary",
            "",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = TaskUpdateResult.model_validate(json.loads(result.stdout))
    assert parsed.task.document.metadata.summary is None


def test_task_update_replaces_tags(project: Path) -> None:
    seed_task(project, "login")
    prepare_project(project).tasks.update("auth", "login", TaskUpdate(tags=["old"]))
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "login",
            "--tag",
            "new",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = TaskUpdateResult.model_validate(json.loads(result.stdout))
    assert parsed.task.document.metadata.tags == ["new"]


def test_task_update_nothing_to_change(project: Path) -> None:
    seed_task(project, "login")
    before = snapshot(project)
    result = runner.invoke(
        app, ["task", "update", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task update"
    assert "Nothing to update" in error.error
    assert snapshot(project) == before


def test_task_update_invalid_status_preserves_task(project: Path) -> None:
    seed_task(project, "login")
    before = snapshot(project)
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "login",
            "--status",
            "bogus",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task update"
    assert "bogus" in error.error
    assert snapshot(project) == before


def test_task_update_unknown_task(project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "missing",
            "--status",
            "done",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task update"


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_task_update_output(project: Path, format_name: str) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "login",
            "--status",
            "done",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            format_name,
        ],
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        parsed = TaskUpdateResult.model_validate(json.loads(result.stdout))
        assert parsed.task.document.metadata.status == "done"
    else:
        assert "Updated task login in example/auth (done)" in result.stdout


def test_task_update_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed_task(project, "seed")
    record = application.tasks.get("auth", "seed")
    update = Mock(return_value=record)
    monkeypatch.setattr(application.tasks, "update", update)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        [
            "task",
            "update",
            "seed",
            "--status",
            "done",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    update.assert_called_once_with("auth", "seed", TaskUpdate(status="done"))
    assert TaskUpdateResult.model_validate(json.loads(result.stdout)).task.name == "seed"
