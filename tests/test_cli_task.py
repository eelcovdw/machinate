import json
import subprocess
import sys
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
    TaskListResult,
    TaskShowResult,
    TaskStatusResult,
)
from machinate.cli.project_setup import prepare_project
from machinate.storage import PlanMetadata, ProjectState, ProjectStateStore, TaskMetadata
from machinate.storage.queries import TaskQuery

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_INTERACTIVE", "MACHI_AGENT"):
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
    assert task.path.as_posix() == "auth/tasks/login.md"
    assert task.document.metadata.status == "todo"
    assert task.document.metadata.created.tzinfo is not None
    assert task.document.body == ""
    assert (project / ".machi/auth/tasks/login.md").is_file()
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


def test_task_add_non_interactive_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["task", "add", "login", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Non-interactive mode requires an explicit plan" in error.error
    assert not (project / ".machi/auth/tasks/login.md").exists()


def test_task_add_no_current_plan(project: Path) -> None:
    result = runner.invoke(app, ["task", "add", "login", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "No current plan is selected" in error.error
    assert not (project / ".machi/auth/tasks/login.md").exists()


def test_task_add_duplicate_preserves_existing(project: Path) -> None:
    first = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert first.exit_code == 0, first.output
    before = snapshot(project)
    duplicate = runner.invoke(
        app, ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert duplicate.exit_code == 1, duplicate.output
    assert "login" in ErrorResult.model_validate_json(duplicate.stderr).error
    assert snapshot(project) == before


@pytest.mark.parametrize("invalid", ["../bad", "a\\b", "a:b", "", ".", "..", "/leading", "trail/"])
def test_task_add_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    before = snapshot(project)
    result = runner.invoke(
        app, ["task", "add", invalid, "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(project) == before


def test_task_add_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["task", "add", "login", "-p", "nope", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "nope" in ErrorResult.model_validate_json(result.stderr).error
    assert not (project / ".machi/nope").exists()


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
        assert str(project / ".machi/auth/tasks/login.md") in result.stdout


@pytest.mark.parametrize(
    ("interactive", "env_format", "flag", "expected"),
    [
        (None, None, None, "text"),
        ("false", None, None, "json"),
        ("true", None, None, "text"),
        ("false", "text", None, "text"),
        (None, "json", None, "json"),
        ("false", "json", "text", "text"),
    ],
)
def test_task_add_format_precedence(  # noqa: PLR0913
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    interactive: str | None,
    env_format: str | None,
    flag: str | None,
    expected: str,
) -> None:
    if interactive is not None:
        monkeypatch.setenv("MACHI_INTERACTIVE", interactive)
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
        ("MACHI_INTERACTIVE", "perhaps", "interactive"),
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
    create = Mock(return_value=seed)
    monkeypatch.setattr(application.tasks, "create", create)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["task", "add", "login", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    create.assert_called_once()
    call_plan, call_name, call_metadata = cast(
        "tuple[str, str, TaskMetadata]", create.call_args.args
    )
    assert call_plan == "auth"
    assert call_name == "login"
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
    shown = runner.invoke(app, ["show", "-p", "auth", "-P", str(project), "--format", "json"])
    assert shown.exit_code == 0, shown.output
    listed = runner.invoke(app, ["list", "-P", str(project), "--format", "json"])
    assert [plan.name for plan in ListResult.model_validate(json.loads(listed.stdout)).plans] == [
        "auth"
    ]


def test_task_add_help() -> None:
    result = runner.invoke(app, ["task", "add", "--help"])
    assert result.exit_code == 0
    assert "--plan" in result.stdout
    assert "--project" in result.stdout
    assert "--format" in result.stdout
    assert not result.stdout.startswith("{")


def test_task_group_help() -> None:
    result = runner.invoke(app, ["task", "--help"])
    assert result.exit_code == 0
    assert "add" in result.stdout
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_task_add_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "add", "login"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_INTERACTIVE", "false")
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


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_checkout_executable_task_add(tmp_path: Path, executable: str) -> None:
    launcher = Path(sys.executable).with_name(executable)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    initialized = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "init", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert initialized.returncode == 0, initialized.stderr
    added = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "add", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert added.returncode == 0, added.stderr
    tasked = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "add", "login", "-p", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert tasked.returncode == 0, tasked.stderr
    assert TaskAddResult.model_validate(json.loads(tasked.stdout)).tasks[0].name == "login"
    assert (fresh / ".machi/auth/tasks/login.md").is_file()
    duplicate = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "add", "login", "-p", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert duplicate.returncode == 1
    help_result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "add", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--plan" in help_result.stdout


def seed_task(project: Path, name: str, summary: str | None = None, body: str = "") -> None:
    prepare_project(project).tasks.create(
        "auth",
        name,
        TaskMetadata(created=datetime(2026, 1, 1, tzinfo=UTC), summary=summary),
        body=body,
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
    assert parsed.tasks[0].path.as_posix() == "auth/tasks/login.md"
    assert parsed.tasks[0].metadata.summary == "Sign in"
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
    seed_task(project, "gamma", body="secret needle")
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


def test_task_list_non_interactive_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["task", "list", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Non-interactive mode requires an explicit plan" in error.error


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


def test_task_list_help() -> None:
    result = runner.invoke(app, ["task", "list", "--help"])
    assert result.exit_code == 0
    assert "--plan" in result.stdout
    assert "--status" in result.stdout
    assert "--format" in result.stdout
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_task_list_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "list", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task list"
    assert "--unknown" in error.error
    factory.assert_not_called()


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_checkout_executable_task_list(tmp_path: Path, executable: str) -> None:
    launcher = Path(sys.executable).with_name(executable)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    for command in (["init", "-P", str(fresh)], ["add", "auth", "-P", str(fresh)]):
        completed = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
            [str(launcher), *command, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
    created = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "add", "login", "-p", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    listed = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "list", "-p", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr
    parsed = TaskListResult.model_validate(json.loads(listed.stdout))
    assert [task.name for task in parsed.tasks] == ["login"]
    help_result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "list", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--status" in help_result.stdout


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
    assert parsed.task.path.as_posix() == "auth/tasks/login.md"
    assert parsed.task.document.metadata.summary == "Sign in"
    assert parsed.task.document.body == "Detailed notes"
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


def test_task_show_non_interactive_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
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


def test_task_show_help() -> None:
    result = runner.invoke(app, ["task", "show", "--help"])
    assert result.exit_code == 0
    assert "--plan" in result.stdout
    assert "--format" in result.stdout
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_task_show_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "show", "login", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task show"
    assert "--unknown" in error.error
    factory.assert_not_called()


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_checkout_executable_task_show(tmp_path: Path, executable: str) -> None:
    launcher = Path(sys.executable).with_name(executable)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    for command in (["init", "-P", str(fresh)], ["add", "auth", "-P", str(fresh)]):
        completed = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
            [str(launcher), *command, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
    subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "add", "login", "-p", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    shown = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [
            str(launcher),
            "task",
            "show",
            "login",
            "-p",
            "auth",
            "-P",
            str(fresh),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert shown.returncode == 0, shown.stderr
    parsed = TaskShowResult.model_validate(json.loads(shown.stdout))
    assert parsed.task.name == "login"
    help_result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "show", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "--plan" in help_result.stdout


def test_task_status_read(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "status", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = TaskStatusResult.model_validate(json.loads(result.stdout))
    assert parsed.task.name == "login"
    assert parsed.task.document.metadata.status == "todo"


def test_task_status_set_persists(project: Path) -> None:
    seed_task(project, "login")
    set_result = runner.invoke(
        app,
        [
            "task",
            "status",
            "login",
            "in-progress",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert set_result.exit_code == 0, set_result.output
    changed = TaskStatusResult.model_validate(json.loads(set_result.stdout))
    assert changed.task.document.metadata.status == "in-progress"
    read_result = runner.invoke(
        app, ["task", "status", "login", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    persisted = TaskStatusResult.model_validate(json.loads(read_result.stdout))
    assert persisted.task.document.metadata.status == "in-progress"


def test_task_status_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(
        app, ["task", "status", "login", "done", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert TaskStatusResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_task_status_does_not_change_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    result = runner.invoke(
        app,
        ["task", "status", "login", "done", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


def test_task_status_invalid_status_preserves_task(project: Path) -> None:
    seed_task(project, "login")
    before = snapshot(project)
    result = runner.invoke(
        app,
        ["task", "status", "login", "bogus", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task status"
    assert "bogus" in error.error
    assert snapshot(project) == before


def test_task_status_unknown_task(project: Path) -> None:
    result = runner.invoke(
        app,
        ["task", "status", "missing", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task status"


def test_task_status_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app,
        ["task", "status", "login", "-p", "nope", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task status"


def test_task_status_non_interactive_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_project(project).plans.set_current("auth")
    seed_task(project, "login")
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["task", "status", "login", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task status"


def test_task_status_no_current_plan(project: Path) -> None:
    seed_task(project, "login")
    result = runner.invoke(app, ["task", "status", "login", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "task status"


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_task_status_output(project: Path, format_name: str) -> None:
    seed_task(project, "login")
    result = runner.invoke(
        app,
        [
            "task",
            "status",
            "login",
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
        parsed = TaskStatusResult.model_validate(json.loads(result.stdout))
        assert parsed.task.document.metadata.status == "done"
    else:
        assert "Task login is done in example/auth" in result.stdout


def test_task_status_formatter_injection(project: Path) -> None:
    seed_task(project, "login")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom,
        ["task", "status", "login", "done", "-p", "auth", "-P", str(project), "--format", "custom"],
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], TaskStatusResult)


def test_task_status_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed_task(project, "seed")
    record = application.tasks.get("auth", "seed")
    set_status = Mock(return_value=record)
    monkeypatch.setattr(application.tasks, "set_status", set_status)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["task", "status", "seed", "done", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    set_status.assert_called_once_with("auth", "seed", "done")
    assert TaskStatusResult.model_validate(json.loads(result.stdout)).task.name == "seed"


def test_task_status_help() -> None:
    result = runner.invoke(app, ["task", "status", "--help"])
    assert result.exit_code == 0
    assert "--plan" in result.stdout
    assert "--format" in result.stdout
    assert not result.stdout.startswith("{")


@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_task_status_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["task", "status", "login", "-p", "auth"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "task status"
    assert "--unknown" in error.error
    factory.assert_not_called()


@pytest.mark.parametrize("executable", ["machi", "machinate"])
def test_checkout_executable_task_status(tmp_path: Path, executable: str) -> None:
    launcher = Path(sys.executable).with_name(executable)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    for command in (["init", "-P", str(fresh)], ["add", "auth", "-P", str(fresh)]):
        completed = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
            [str(launcher), *command, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
    subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "task", "add", "login", "-p", "auth", "-P", str(fresh), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    updated = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [
            str(launcher),
            "task",
            "status",
            "login",
            "done",
            "-p",
            "auth",
            "-P",
            str(fresh),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert updated.returncode == 0, updated.stderr
    parsed = TaskStatusResult.model_validate(json.loads(updated.stdout))
    assert parsed.task.document.metadata.status == "done"
    read_back = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [
            str(launcher),
            "task",
            "status",
            "login",
            "-p",
            "auth",
            "-P",
            str(fresh),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert read_back.returncode == 0, read_back.stderr
    persisted = TaskStatusResult.model_validate(json.loads(read_back.stdout))
    assert persisted.task.document.metadata.status == "done"
