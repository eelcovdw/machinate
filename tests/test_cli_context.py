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
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ContextUpdateResult,
    ErrorResult,
    ListResult,
)
from machinate.cli.project_setup import prepare_project
from machinate.models.context import ContextUpdate
from machinate.storage import ContextMetadata, PlanMetadata, ProjectState, ProjectStateStore

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


def test_context_add_explicit_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = ContextAddResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan == "auth"
    context = parsed.contexts[0]
    assert context.name == "spec"
    assert context.path.as_posix() == "plans/auth/context/spec.md"
    assert context.document.metadata.created.tzinfo is not None
    assert context.document.metadata.summary is None
    assert context.document.body == ""
    assert (project / ".machi/plans/auth/context/spec.md").is_file()
    assert read_state(project).current_plan is None


def test_context_add_current_plan(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["context", "add", "spec", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ContextAddResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_context_add_never_changes_selection(project: Path) -> None:
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(
        app, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


def test_context_add_multiple(project: Path) -> None:
    result = runner.invoke(
        app,
        ["context", "add", "spec", "notes", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    names = [
        context.name
        for context in ContextAddResult.model_validate(json.loads(result.stdout)).contexts
    ]
    assert names == ["spec", "notes"]


def test_context_add_batch_partial_success(project: Path) -> None:
    """C2: an existing name must not abort the batch or swallow later names."""
    prepare_project(project).contexts.create(
        "auth", "existing", ContextMetadata(created=_DEFAULT_CREATED)
    )
    result = runner.invoke(
        app,
        [
            "context",
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
    parsed = ContextAddResult.model_validate(json.loads(result.stdout))
    assert [context.name for context in parsed.contexts] == ["new", "later"]
    assert [error.name for error in parsed.errors] == ["existing", "../bad"]
    assert "Already exists" in parsed.errors[0].error
    assert "Expected a nonempty name" in parsed.errors[1].error
    assert (project / ".machi/plans/auth/context/new.md").exists()
    assert (project / ".machi/plans/auth/context/later.md").exists()
    assert (project / ".machi/plans/auth/context/existing.md").exists()  # Not overwritten.


def test_context_add_batch_partial_success_text_reports_errors(project: Path) -> None:
    """Text output must surface rejected names, not only exit non-zero."""
    prepare_project(project).contexts.create(
        "auth", "existing", ContextMetadata(created=_DEFAULT_CREATED)
    )
    result = runner.invoke(
        app,
        [
            "context",
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
    assert "Created 1 context document(s)" in result.stdout
    assert "Not created:" in result.stdout
    assert "existing" in result.stdout
    assert "Already exists" in result.stdout
    assert "../bad" in result.stdout
    assert "Expected a nonempty name" in result.stdout
    assert (project / ".machi/plans/auth/context/new.md").exists()


def test_context_add_automation_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["context", "add", "spec", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Automation mode requires an explicit plan" in error.error
    assert not (project / ".machi/plans/auth/context/spec.md").exists()


def test_context_add_no_current_plan(project: Path) -> None:
    result = runner.invoke(app, ["context", "add", "spec", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "No current plan is selected" in error.error
    assert not (project / ".machi/plans/auth/context/spec.md").exists()


def test_context_add_duplicate_preserves_existing(project: Path) -> None:
    """A duplicate is now a partial-failure result, not a global error."""
    first = runner.invoke(
        app, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert first.exit_code == 0, first.output
    before = snapshot(project)
    duplicate = runner.invoke(
        app, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert duplicate.exit_code == 1, duplicate.output
    parsed = ContextAddResult.model_validate(json.loads(duplicate.stdout))
    assert parsed.contexts == []
    assert [error.name for error in parsed.errors] == ["spec"]
    assert "Already exists" in parsed.errors[0].error
    assert snapshot(project) == before


@pytest.mark.parametrize("invalid", ["../bad", "a\\b", "a:b", "", ".", "..", "/leading", "trail/"])
def test_context_add_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    before = snapshot(project)
    result = runner.invoke(
        app, ["context", "add", invalid, "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    parsed = ContextAddResult.model_validate(json.loads(result.stdout))
    assert parsed.contexts == []
    assert [error.name for error in parsed.errors] == [invalid]
    assert "Expected a nonempty name" in parsed.errors[0].error
    assert snapshot(project) == before


def test_context_add_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app, ["context", "add", "spec", "-p", "nope", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "nope" in ErrorResult.model_validate_json(result.stderr).error
    assert not (project / ".machi/plans/nope").exists()


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_context_add_output(project: Path, format_name: str) -> None:
    result = runner.invoke(
        app, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", format_name]
    )
    assert result.exit_code == 0, result.output
    if format_name == "json":
        parsed = ContextAddResult.model_validate(json.loads(result.stdout))
        assert parsed.contexts[0].name == "spec"
    else:
        assert "Created 1 context document(s) in example/auth" in result.stdout
        assert str(project / ".machi/plans/auth/context/spec.md") in result.stdout


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
def test_context_add_format_precedence(  # noqa: PLR0913
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
    args = ["context", "add", "spec", "-p", "auth", "-P", str(project)]
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
def test_context_add_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["context", "add", "spec", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_context_add_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], ContextAddResult)


def test_context_add_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    application = prepare_project(project)
    seed = application.contexts.create(
        "auth", "seed", ContextMetadata(created=datetime(2026, 1, 1, tzinfo=UTC))
    )
    create_batch = Mock(return_value=([seed], []))
    monkeypatch.setattr(application.contexts, "create_batch", create_batch)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    create_batch.assert_called_once()
    call_plan, call_names, call_metadata = cast(
        "tuple[str, list[str], ContextMetadata]", create_batch.call_args.args
    )
    assert call_plan == "auth"
    assert call_names == ["spec"]
    assert call_metadata.created.tzinfo is not None
    assert ContextAddResult.model_validate(json.loads(result.stdout)).contexts[0].name == "seed"


def test_context_add_stamps_aware_utc(project: Path) -> None:
    before = datetime.now(UTC)
    result = runner.invoke(
        app, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    after = datetime.now(UTC)
    assert result.exit_code == 0, result.output
    created = (
        ContextAddResult.model_validate(json.loads(result.stdout))
        .contexts[0]
        .document.metadata.created
    )
    assert created.tzinfo is not None
    assert before <= created <= after


def test_context_add_then_show_and_list(project: Path) -> None:
    added = runner.invoke(
        app, ["context", "add", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
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
def test_context_add_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["context", "add", "spec"]
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
    assert error.command == "context add"
    assert "--unknown" in error.error
    factory.assert_not_called()


def test_context_add_parser_error_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["context", "add", "spec", "--unknown", "--format=custom"])
    assert result.exit_code == 2
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[0], ErrorResult)


def seed_context(
    project: Path,
    name: str,
    *,
    summary: str | None = None,
    body: str = "",
    created: datetime = _DEFAULT_CREATED,
) -> None:
    if summary is not None and not body:
        body = summary
    prepare_project(project).contexts.create("auth", name, ContextMetadata(created=created), body)


def test_context_list_explicit_plan(project: Path) -> None:
    seed_context(project, "spec")
    seed_context(project, "notes")
    result = runner.invoke(
        app, ["context", "list", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = ContextListResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.plan == "auth"
    assert [context.name for context in parsed.contexts] == ["notes", "spec"]


def test_context_list_current_plan(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["context", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ContextListResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_context_list_empty(project: Path) -> None:
    result = runner.invoke(
        app, ["context", "list", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    assert ContextListResult.model_validate(json.loads(result.stdout)).contexts == []


def test_context_list_does_not_change_selection(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["context", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


def test_context_list_automation_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["context", "list", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Automation mode requires an explicit plan" in error.error


def test_context_list_no_current_plan(project: Path) -> None:
    result = runner.invoke(app, ["context", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "No current plan is selected" in error.error


def test_context_list_search(project: Path) -> None:
    seed_context(project, "spec")
    seed_context(project, "notes")
    result = runner.invoke(
        app,
        [
            "context",
            "list",
            "-p",
            "auth",
            "-P",
            str(project),
            "--search",
            "spec",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    names = [
        context.name
        for context in ContextListResult.model_validate(json.loads(result.stdout)).contexts
    ]
    assert names == ["spec"]


def test_context_list_limit_and_descending(project: Path) -> None:
    for name in ("a", "b", "c"):
        seed_context(project, name)
    result = runner.invoke(
        app,
        [
            "context",
            "list",
            "-p",
            "auth",
            "-P",
            str(project),
            "--limit",
            "2",
            "--descending",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    names = [
        context.name
        for context in ContextListResult.model_validate(json.loads(result.stdout)).contexts
    ]
    assert names == ["c", "b"]


def test_context_list_invalid_limit(project: Path) -> None:
    result = runner.invoke(
        app,
        ["context", "list", "-p", "auth", "-P", str(project), "--limit", "0", "--format", "json"],
    )
    assert result.exit_code == 1, result.output
    assert "limit" in ErrorResult.model_validate_json(result.stderr).error.lower()


def test_context_list_text_output(project: Path) -> None:
    seed_context(project, "spec", summary="The spec")
    result = runner.invoke(app, ["context", "list", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "example / auth" in result.stdout
    assert "spec" in result.stdout
    assert "The spec" in result.stdout


def test_context_list_empty_text(project: Path) -> None:
    result = runner.invoke(app, ["context", "list", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "No contexts found." in result.stdout


def test_context_list_formatter_injection(project: Path) -> None:
    seed_context(project, "spec")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom, ["context", "list", "-p", "auth", "-P", str(project), "--format", "custom"]
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], ContextListResult)


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_context_list_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["context", "list"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "context list"
    factory.assert_not_called()


def test_context_show_explicit_plan(project: Path) -> None:
    seed_context(project, "spec", summary="The spec", body="# Spec\n\nDetails.\n")
    result = runner.invoke(
        app, ["context", "show", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = ContextShowResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.plan == "auth"
    assert parsed.context.name == "spec"
    assert parsed.context.path.as_posix() == "plans/auth/context/spec.md"
    assert parsed.context.document.get_or_derive_summary() == "Details."
    assert parsed.context.document.body == "# Spec\n\nDetails.\n"
    assert parsed.context.document.metadata.created.tzinfo is not None


def test_context_show_current_plan(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["context", "show", "spec", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ContextShowResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_context_show_does_not_change_selection(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["context", "show", "spec", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


def test_context_show_automation_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["context", "show", "spec", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Automation mode requires an explicit plan" in error.error


def test_context_show_no_current_plan(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(app, ["context", "show", "spec", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "No current plan is selected" in ErrorResult.model_validate_json(result.stderr).error


def test_context_show_unknown_context(project: Path) -> None:
    result = runner.invoke(
        app, ["context", "show", "missing", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "missing" in ErrorResult.model_validate_json(result.stderr).error


def test_context_show_unknown_plan(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(
        app, ["context", "show", "spec", "-p", "nope", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "nope" in ErrorResult.model_validate_json(result.stderr).error


@pytest.mark.parametrize("invalid", ["../bad", "a\\b", "a:b", "", ".", ".."])
def test_context_show_invalid_name(project: Path, invalid: str) -> None:
    result = runner.invoke(
        app, ["context", "show", invalid, "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "Expected a nonempty name" in ErrorResult.model_validate_json(result.stderr).error


def test_context_show_text_output(project: Path) -> None:
    seed_context(project, "spec", summary="The spec", body="# Spec\n\nDetails.")
    result = runner.invoke(app, ["context", "show", "spec", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "Context spec" in result.stdout
    assert "example / auth" in result.stdout
    assert "Summary: Details." in result.stdout
    assert "# Spec\n\nDetails." in result.stdout


def test_context_show_text_output_without_body(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(app, ["context", "show", "spec", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "Context spec" in result.stdout
    assert "Summary:" not in result.stdout


def test_context_show_formatter_injection(project: Path) -> None:
    seed_context(project, "spec")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom,
        ["context", "show", "spec", "-p", "auth", "-P", str(project), "--format", "custom"],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], ContextShowResult)


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_context_show_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["context", "show", "spec"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "context show"
    factory.assert_not_called()


def test_context_info_explicit_plan(project: Path) -> None:
    seed_context(project, "spec", summary="The spec", body="# Spec\n\nDetails.\n")
    result = runner.invoke(
        app, ["context", "info", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    parsed = ContextInfoResult.model_validate(json.loads(result.stdout))
    assert parsed.project.name == "example"
    assert parsed.plan == "auth"
    assert parsed.context.name == "spec"
    assert parsed.context.path.as_posix() == "plans/auth/context/spec.md"
    assert parsed.context.summary == "Details."
    assert parsed.context.last_activity_at.tzinfo is not None


def test_context_info_omits_body(project: Path) -> None:
    seed_context(project, "spec", summary="The spec", body="# Spec\n\nDetails.\n")
    result = runner.invoke(
        app, ["context", "info", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    payload = cast("dict[str, object]", json.loads(result.stdout)["context"])
    assert "document" not in payload
    assert "body" not in payload


def test_context_info_current_plan(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["context", "info", "spec", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert ContextInfoResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_context_info_does_not_change_selection(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(app, ["context", "info", "spec", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_state(project).current_plan == "auth"


def test_context_info_automation_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["context", "info", "spec", "-P", str(project)])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "Automation mode requires an explicit plan" in error.error


def test_context_info_unknown_context(project: Path) -> None:
    result = runner.invoke(
        app, ["context", "info", "missing", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "missing" in ErrorResult.model_validate_json(result.stderr).error


def test_context_info_text_output(project: Path) -> None:
    seed_context(project, "spec", summary="The spec", body="# Spec\n\nDetails.")
    result = runner.invoke(app, ["context", "info", "spec", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "Context spec" in result.stdout
    assert "example / auth" in result.stdout
    assert "Summary: Details." in result.stdout
    assert "# Spec" not in result.stdout


def test_context_info_text_output_without_summary(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(app, ["context", "info", "spec", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0, result.output
    assert "Context spec" in result.stdout
    assert "Summary:" not in result.stdout


def test_context_info_formatter_injection(project: Path) -> None:
    seed_context(project, "spec")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom,
        ["context", "info", "spec", "-p", "auth", "-P", str(project), "--format", "custom"],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], ContextInfoResult)


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_context_info_parser_errors_use_json(monkeypatch: pytest.MonkeyPatch, source: str) -> None:
    args = ["context", "info", "spec"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, "--unknown"])
    assert result.exit_code == 2, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "context info"
    factory.assert_not_called()


def test_context_update_sets_summary(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
            "--summary",
            "The spec",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    parsed = ContextUpdateResult.model_validate(json.loads(result.stdout))
    assert parsed.context.document.metadata.summary == "The spec"


def test_context_update_clears_summary(project: Path) -> None:
    seed_context(project, "spec", summary="The spec")
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
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
    parsed = ContextUpdateResult.model_validate(json.loads(result.stdout))
    assert parsed.context.document.metadata.summary is None


def test_context_update_replaces_tags(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).contexts.update("auth", "spec", ContextUpdate(tags=["old"]))
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
            "--tag",
            "new",
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
    parsed = ContextUpdateResult.model_validate(json.loads(result.stdout))
    assert parsed.context.document.metadata.tags == ["new", "backend"]


def test_context_update_current_plan(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(
        app,
        ["context", "update", "spec", "--summary", "New", "-P", str(project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    assert ContextUpdateResult.model_validate(json.loads(result.stdout)).plan == "auth"


def test_context_update_does_not_change_selection(project: Path) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
            "--summary",
            "New",
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


def test_context_update_nothing_to_change(project: Path) -> None:
    seed_context(project, "spec")
    before = snapshot(project)
    result = runner.invoke(
        app, ["context", "update", "spec", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "context update"
    assert "Nothing to update" in error.error
    assert snapshot(project) == before


def test_context_update_unknown_context(project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "missing",
            "--summary",
            "x",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "context update"


def test_context_update_unknown_plan(project: Path) -> None:
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
            "--summary",
            "x",
            "-p",
            "nope",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "context update"


def test_context_update_automation_requires_plan(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_context(project, "spec")
    prepare_project(project).plans.set_current("auth")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["context", "update", "spec", "--summary", "x", "-P", str(project)])
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "context update"


def test_context_update_no_current_plan(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(
        app, ["context", "update", "spec", "--summary", "x", "-P", str(project), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "context update"


@pytest.mark.parametrize("invalid", ["", "../bad"])
def test_context_update_invalid_name_preserves_target(project: Path, invalid: str) -> None:
    seed_context(project, "spec")
    before = snapshot(project)
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            invalid,
            "--summary",
            "x",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1, result.output
    assert snapshot(project) == before


def test_context_update_text_output(project: Path) -> None:
    seed_context(project, "spec")
    result = runner.invoke(
        app,
        [
            "context",
            "update",
            "spec",
            "--summary",
            "New",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "text",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Updated context spec in example/auth" in result.stdout


@pytest.mark.parametrize(
    ("automation", "env_format", "flag", "expected"),
    [
        (None, None, None, "text"),
        ("true", None, None, "json"),
        (None, "json", None, "json"),
        ("true", "json", "text", "text"),
    ],
)
def test_context_update_format_precedence(  # noqa: PLR0913
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    automation: str | None,
    env_format: str | None,
    flag: str | None,
    expected: str,
) -> None:
    seed_context(project, "spec")
    if automation is not None:
        monkeypatch.setenv("MACHI_AUTOMATION", automation)
    if env_format is not None:
        monkeypatch.setenv("MACHI_FORMAT", env_format)
    args = ["context", "update", "spec", "--summary", "x", "-p", "auth", "-P", str(project)]
    if flag is not None:
        args.extend(["--format", flag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{") == (expected == "json")


def test_context_update_formatter_injection(project: Path) -> None:
    seed_context(project, "spec")
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(
        custom,
        [
            "context",
            "update",
            "spec",
            "--summary",
            "x",
            "-p",
            "auth",
            "-P",
            str(project),
            "--format",
            "custom",
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], ContextUpdateResult)


def test_context_update_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed_context(project, "spec")
    application = prepare_project(project)
    record = application.contexts.get("auth", "spec")
    update = Mock(return_value=record)
    monkeypatch.setattr(application.contexts, "update", update)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(prepare_project=factory)),
        [
            "context",
            "update",
            "spec",
            "--summary",
            "x",
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
    update.assert_called_once_with("auth", "spec", ContextUpdate(summary="x"))
    assert ContextUpdateResult.model_validate(json.loads(result.stdout)).context.name == "spec"


@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_context_update_parser_errors_use_json(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    args = ["context", "update", "spec", "-p", "auth"]
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
    assert error.command == "context update"
    assert "--unknown" in error.error
    factory.assert_not_called()
