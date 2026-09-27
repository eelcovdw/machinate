import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast, override
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.formatting import Formatter
from machinate.cli.models import (
    CommandResult,
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


def test_task_add_never_changes_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


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


def test_task_add_automation_requires_plan(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["task", "add", "login", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Automation mode requires an explicit plan" in error.error
    assert not (project / ".machi/plans/auth/tasks/login.md").exists()


def test_task_add_no_current_plan(project: Path) -> None:
    result = runner.invoke(app, ["task", "add", "login", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "No current plan is selected" in error.error
    assert not (project / ".machi/plans/auth/tasks/login.md").exists()


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


def test_task_add_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "add", "login", "-p", "nope", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "nope" in ErrorResult.model_validate_json(result.stderr).error
    assert not (project / ".machi/plans/nope").exists()


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


@pytest.mark.parametrize(
    ("automation", "env_format", "flag", "expected"),
    [
        (None, None, None, "text"),
        ("true", None, None, "json"),
        ("false", None, None, "text"),
        ("true", "text", None, "text"),
        (None, "json", None, "json"),
        ("true", "json", "text", "text"),
    ],
)
def test_task_add_format_precedence(  # noqa: PLR0913
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    automation: str | None,
    env_format: str | None,
    flag: str | None,
    expected: str,
) -> None:
    if automation is not None:
        monkeypatch.setenv("MACHI_AUTOMATION", automation)
    if env_format is not None:
        monkeypatch.setenv("MACHI_FORMAT", env_format)
    args = ["task", "add", "login", "-p", "auth", "-P", str(project)]
    if flag is not None:
        args.extend(["--format", flag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{") == (expected == "json")


@pytest.mark.parametrize(
    ("env_name", "env_value", "field"),
    [
        ("MACHI_AUTOMATION", "perhaps", "automation"),
        ("MACHI_FORMAT", "human", "format"),
    ],
)
def test_task_add_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["task", "add", "login", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_task_add_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], TaskAddResult)


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


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_task_add_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "add", "login"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task add"
    assert "--unknown" in error.error
    factory.assert_not_called()


def test_task_add_parser_error_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["task", "add", "login", "--unknown", "--format=custom"])
    assert result.exit_code == 2
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[0], ErrorResult)


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


def test_task_list_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(app, ["task", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert TaskListResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_task_list_does_not_change_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "list", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


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


def test_task_list_automation_requires_plan(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["task", "list", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Automation mode requires an explicit plan" in error.error


def test_task_list_no_current_plan(project: Path) -> None:
    result = runner.invoke(app, ["task", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "No current plan is selected" in error.error


def test_task_list_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "list", "-p", "nope", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "nope" in ErrorResult.model_validate_json(result.stderr).error


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


def test_task_list_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["task", "list", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], TaskListResult)


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


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_task_list_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "list", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task list"
    assert "--unknown" in error.error
    factory.assert_not_called()


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


def test_task_show_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(app, ["task", "show", "login", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert TaskShowResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_task_show_does_not_change_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "show", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


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


def test_task_show_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "show", "login", "-p", "nope", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task show"


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


def test_task_show_automation_requires_plan(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["task", "show", "login", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task show"


def test_task_show_no_current_plan(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(app, ["task", "show", "login", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task show"


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


def test_task_show_formatter_injection(project: Path) -> None:
    seed_task(project, "login")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["task", "show", "login", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], TaskShowResult)


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


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_task_show_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "show", "login", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task show"
    assert "--unknown" in error.error
    factory.assert_not_called()


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


def test_task_info_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(app, ["task", "info", "login", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert TaskInfoResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_task_info_does_not_change_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "info", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


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


def test_task_info_automation_requires_plan(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["task", "info", "login", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task info"


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


def test_task_info_formatter_injection(project: Path) -> None:
    seed_task(project, "login")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["task", "info", "login", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], TaskInfoResult)


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_task_info_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "info", "login", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task info"
    assert "--unknown" in error.error
    factory.assert_not_called()


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


def test_task_update_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "update", "login", "--status", "done", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert TaskUpdateResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_task_update_does_not_change_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
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
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


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


def test_task_update_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "task",
            "update",
            "login",
            "--status",
            "done",
            "-p",
            "nope",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task update"


def test_task_update_automation_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["task", "update", "login", "--status", "done", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task update"


def test_task_update_no_current_plan(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "update", "login", "--status", "done", "-P", str(project), "--format", "json"]
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


def test_task_update_formatter_injection(project: Path) -> None:
    seed_task(project, "login")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom,
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
            "custom",
        ],
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], TaskUpdateResult)


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


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_task_update_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "update", "login", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task update"
    assert "--unknown" in error.error
    factory.assert_not_called()
