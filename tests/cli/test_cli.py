import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import override
from unittest.mock import Mock

import pytest
from harness import DEFAULT_DEPENDENCIES, DEFAULT_SETTINGS, make_settings
from typer.testing import CliRunner

from machinate.cli.cli import create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.formatting import Formatter
from machinate.cli.models import CommandResult, ErrorResult, ListResult
from machinate.cli.project_setup import prepare_project
from machinate.storage import (
    Document,
    DocumentStore,
    Layout,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
)
from machinate.storage.queries import PlanQuery

runner = CliRunner()
app = create_cli(DEFAULT_DEPENDENCIES)


def populate(project: Path) -> None:
    store = DocumentStore(project / ".machi")
    for name, status in (("beta", "done"), ("alpha", "active")):
        store.create(
            Layout().plan(name),
            Document(
                metadata=PlanMetadata.model_validate(
                    {
                        "created": datetime(2026, 9, 22, tzinfo=UTC),
                        "status": status,
                        "summary": f"Summary of {name}",
                    }
                ),
                body="needle in body",
            ),
        )


def test_explicit_and_upward(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    populate(project)
    child = project / "nested/deep"
    child.mkdir(parents=True)
    monkeypatch.chdir(child)
    for args in (["-P", str(project)], []):
        result = runner.invoke(app, ["plan", "list", *args, "--format", "json"])
        assert result.exit_code == 0, result.output
        parsed = ListResult.model_validate(json.loads(result.stdout))
        assert parsed.project.directory == project
        assert parsed.project.storage == project / ".machi"
        assert parsed.project.name == "example"
        assert [plan.name for plan in parsed.plans] == ["alpha", "beta"]


def test_nearest_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = project / "nested"
    ProjectStateStore(nested / ".machi/machinate.toml").write(ProjectState(project_name="inner"))
    monkeypatch.chdir(nested)
    result = runner.invoke(app, ["plan", "list", "--format", "json"])
    assert ListResult.model_validate(json.loads(result.stdout)).project.name == "inner"


def test_list_alias_matches_plan_list(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    populate(project)
    monkeypatch.chdir(project)
    alias = runner.invoke(app, ["list", "--format", "json"])
    canonical = runner.invoke(app, ["plan", "list", "--format", "json"])
    assert alias.exit_code == 0, alias.output
    assert alias.stdout == canonical.stdout


def test_list_alias_is_hidden() -> None:
    hidden = {command.name for command in app.registered_commands if command.hidden}
    assert "list" in hidden
    visible = {group.name for group in app.registered_groups if group.hidden is not True}
    assert "plan" in visible


@pytest.mark.parametrize(
    "kind",
    ["missing", "file", "empty", "bad-toml", "bad-state", "symlink-file", "symlink-dangling"],
)
def test_invalid_projects_no_fallback(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    nested = project / "nested"
    nested.mkdir()
    storage = nested / ".machi"
    if kind == "file":
        storage.write_text("bad")
    elif kind == "symlink-file":
        target = nested / "target-file"
        target.write_text("x")
        storage.symlink_to(target)
    elif kind == "symlink-dangling":
        storage.symlink_to(nested / "nowhere", target_is_directory=True)
    elif kind != "missing":
        storage.mkdir()
        if kind in {"bad-toml", "bad-state"}:
            (storage / "machinate.toml").write_text("[" if kind == "bad-toml" else "x = 1")
    monkeypatch.chdir(nested)
    invocations = [["plan", "list", "-P", str(nested), "--format", "json"]]
    if kind != "missing":
        invocations.append(["plan", "list", "--format", "json"])
    for args in invocations:
        result = runner.invoke(app, args)
        assert result.exit_code == 1, result.output
        assert result.stdout == ""
        error = ErrorResult.model_validate_json(result.stderr)
        assert str(nested) in error.error


def test_missing_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["plan", "list", "--format", "json"])
    assert result.exit_code == 1
    assert "No initialized project" in ErrorResult.model_validate_json(result.stderr).error


def test_symlinked_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = tmp_path / "real"
    ProjectStateStore(real / ".machi/machinate.toml").write(ProjectState(project_name="linked"))
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".machi").symlink_to(real / ".machi", target_is_directory=True)
    monkeypatch.chdir(linked)
    for args in (["-P", str(linked)], []):
        result = runner.invoke(app, ["plan", "list", *args, "--format", "json"])
        assert result.exit_code == 0, result.output
        parsed = ListResult.model_validate(json.loads(result.stdout))
        assert parsed.project.name == "linked"
        assert parsed.project.storage == linked / ".machi"


def test_query_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    populate(project)
    application = prepare_project(project)
    summaries = application.plans.list()[::-1]
    listing = Mock(return_value=summaries)
    monkeypatch.setattr(application.plans, "list", listing)
    factory = Mock(return_value=application)
    result = runner.invoke(
        create_cli(Dependencies(settings=DEFAULT_SETTINGS, prepare_project=factory)),
        [
            "plan",
            "list",
            "-P",
            str(project),
            "--format",
            "json",
            "--status",
            "active",
            "--status",
            "done",
            "--sort",
            "updated",
            "--descending",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    factory.assert_called_once_with(project)
    listing.assert_called_once_with(
        PlanQuery(
            statuses={"active", "done"},
            sort="updated",
            descending=True,
            limit=1,
        )
    )
    assert ListResult.model_validate(json.loads(result.stdout)).plans == summaries


def test_query_integration(project: Path) -> None:
    populate(project)
    result = runner.invoke(
        app,
        [
            "plan",
            "list",
            "-P",
            str(project),
            "--format",
            "json",
            "--status",
            "done",
        ],
    )
    assert result.exit_code == 0, result.output
    assert [p.name for p in ListResult.model_validate(json.loads(result.stdout)).plans] == ["beta"]


@pytest.mark.parametrize("populated", [False, True])
@pytest.mark.parametrize("format_name", ["text", "json"])
def test_output(project: Path, populated: bool, format_name: str) -> None:
    if populated:
        populate(project)
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", format_name])
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert len(ListResult.model_validate(json.loads(result.stdout)).plans) == (
            2 if populated else 0
        )
    else:
        assert "example" in result.stdout


@pytest.mark.parametrize(
    ("settings_kwargs", "flag", "expected"),
    [
        ({}, None, "text"),
        ({"automation": True}, None, "json"),
        ({"automation": False}, None, "text"),
        ({"automation": True, "format": "text"}, None, "text"),
        ({"format": "json"}, None, "json"),
        ({"automation": True, "format": "json"}, "text", "text"),
    ],
)
def test_format_precedence(
    project: Path,
    settings_kwargs: dict[str, object],
    flag: str | None,
    expected: str,
) -> None:
    format_value = settings_kwargs.get("format")
    dependencies = Dependencies(
        settings=make_settings(
            automation=bool(settings_kwargs.get("automation", False)),
            format_name=format_value if isinstance(format_value, str) else None,
        )
    )
    args = ["plan", "list", "-P", str(project)]
    if flag is not None:
        args.extend(["--format", flag])
    result = runner.invoke(create_cli(dependencies), args)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{") == (expected == "json")


@pytest.mark.parametrize(
    "args",
    [
        ["--format", "human"],
        ["--status", "bad"],
        ["--sort", "bad"],
        ["--limit", "0"],
        ["--limit", "abc"],
    ],
)
def test_invalid_options(project: Path, args: list[str]) -> None:
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json", *args])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(settings=DEFAULT_SETTINGS, formatters={"custom": formatter}))
    result = runner.invoke(custom, ["plan", "list", "-P", str(project), "--format", "custom"])
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], ListResult)
    result = runner.invoke(
        custom, ["plan", "list", "-P", str(project / "missing"), "--format", "custom"]
    )
    assert result.exit_code == 1
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[1], ErrorResult)


def test_log_level_setting_enables_debug_diagnostics(project: Path) -> None:
    logger = logging.getLogger("machinate")
    dependencies = Dependencies(settings=make_settings(log_level="DEBUG"))
    target = project / ".machi/plans/bare/plan.md"
    target.parent.mkdir(parents=True)
    target.write_text("no frontmatter here")
    try:
        result = runner.invoke(
            create_cli(dependencies), ["plan", "list", "-P", str(project), "--format", "json"]
        )
        assert result.exit_code == 0
        assert "DEBUG" in result.stderr
        assert "machinate.storage.document_store" in result.stderr
        assert "plans/bare/plan.md" in result.stderr
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)


def test_read_only_and_malformed_document(project: Path) -> None:
    prepare_project(project).plans.project_state_store.write(
        ProjectState(project_name="example", current_plan="dangling")
    )
    populate(project)

    def snapshot() -> dict[Path, tuple[bytes | None, int]]:
        return {
            p: (p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns)
            for p in project.rglob("*")
        }

    before = snapshot()
    for format_name in ("json", "text"):
        result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", format_name])
        assert result.exit_code == 0
    assert snapshot() == before
    assert prepare_project(project).plans.project_state_store.read().current_plan == "dangling"
    (project / ".machi/plans/alpha/plan.md").write_text("---\nsummary: missing date\n---\n")
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1
    error = ErrorResult.model_validate_json(result.stderr)
    assert "alpha/plan.md" in error.error
    assert error.project is not None
    assert error.project.directory == project


@pytest.mark.parametrize("invalid", [["--limit"], ["--unknown"]])
@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_parser_errors_use_json(
    invalid: list[str],
    source: str,
) -> None:
    args = ["plan", "list"]
    settings = DEFAULT_SETTINGS
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        settings = make_settings(format_name="json")
    else:
        settings = make_settings(automation=True)
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    dependencies = Dependencies(settings=settings, prepare_project=factory)
    result = runner.invoke(create_cli(dependencies), [*args, *invalid])
    assert result.exit_code == 2
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert invalid[0] in error.error
    factory.assert_not_called()


def test_parser_error_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(settings=DEFAULT_SETTINGS, formatters={"custom": formatter}))
    result = runner.invoke(custom, ["plan", "list", "--unknown", "--format=custom"])
    assert result.exit_code == 2
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[0], ErrorResult)


def test_parser_error_format_override() -> None:
    dependencies = Dependencies(settings=make_settings(format_name="json"))
    result = runner.invoke(
        create_cli(dependencies), ["plan", "list", "--format", "text", "--limit"]
    )
    assert result.exit_code == 2
    assert not result.stderr.startswith("{")


def test_group_parser_errors_use_json() -> None:
    """C5: group failures follow the same formatting policy as leaf commands."""
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    custom = create_cli(
        Dependencies(settings=make_settings(automation=True), prepare_project=factory)
    )

    unknown_command = runner.invoke(custom, ["task", "oops"])
    assert unknown_command.exit_code == 2
    assert unknown_command.stdout == ""
    parsed = ErrorResult.model_validate_json(unknown_command.stderr)
    assert parsed.command == "task"
    assert parsed.error

    top_level = runner.invoke(custom, ["--definitely-not-an-option"])
    assert top_level.exit_code == 2
    assert top_level.stdout == ""
    assert ErrorResult.model_validate_json(top_level.stderr).error

    group_option = runner.invoke(custom, ["task", "--definitely-not-an-option"])
    assert group_option.exit_code == 2
    assert group_option.stdout == ""
    assert ErrorResult.model_validate_json(group_option.stderr).error
    factory.assert_not_called()


def test_group_parser_errors_use_text() -> None:
    dependencies = Dependencies(settings=make_settings(format_name="text"))
    result = runner.invoke(create_cli(dependencies), ["task", "oops"])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert not result.stderr.startswith("{")


def test_group_parser_error_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    dependencies = Dependencies(
        settings=make_settings(format_name="custom"), formatters={"custom": formatter}
    )
    custom = create_cli(dependencies)
    result = runner.invoke(custom, ["task", "oops"])
    assert result.exit_code == 2
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[0], ErrorResult)


def test_group_help_still_prints() -> None:
    """C5 must not swallow the no-args help path for groups."""
    dependencies = Dependencies(settings=make_settings(format_name="json"))
    result = runner.invoke(create_cli(dependencies), ["task"])
    assert result.exit_code == 2
    assert result.stdout
    assert result.stderr == ""
