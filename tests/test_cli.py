import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import override
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
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


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_INTERACTIVE", "MACHI_LOG_LEVEL", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(UPath(root / ".machi/machinate.toml")).write(
        ProjectState(project_name="example", current_plan="dangling")
    )
    return root


def populate(project: Path) -> None:
    store = DocumentStore(UPath(project / ".machi"))
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
    ProjectStateStore(UPath(nested / ".machi/machinate.toml")).write(
        ProjectState(project_name="inner")
    )
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
    help_output = runner.invoke(app, ["--help"]).stdout
    assert "│ list" not in help_output
    assert "│ plan" in help_output


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
    ProjectStateStore(UPath(real / ".machi/machinate.toml")).write(
        ProjectState(project_name="linked")
    )
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
        create_cli(Dependencies(prepare_project=factory)),
        [
            "plan",
            "list",
            "-P",
            str(project),
            "--format",
            "json",
            "--search",
            "absent",
            "--search-body",
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
            search="absent",
            search_body=True,
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
            "--search",
            "needle",
            "--search-body",
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
        assert str(project / ".machi") in result.stdout
        assert ("alpha" if populated else "No plans found.") in result.stdout


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
def test_format_precedence(  # noqa: PLR0913
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
    monkeypatch.setenv("MACHI_AGENT", "true")
    args = ["plan", "list", "-P", str(project)]
    if flag is not None:
        args.extend(["--format", flag])
    result = runner.invoke(app, args)
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
    if "human" in args:
        assert "Available formats: json, text" in error.error


@pytest.mark.parametrize(
    ("env_name", "env_value", "field"),
    [
        ("MACHI_INTERACTIVE", "perhaps", "interactive"),
        ("MACHI_FORMAT", "human", "format"),
    ],
)
def test_invalid_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["plan", "list", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


def test_invalid_env_format_is_not_ignored_by_flag(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "human")
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1
    assert "format" in ErrorResult.model_validate_json(result.stderr).error


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_formatter_injection(project: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
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


def test_log_level_env_enables_debug_diagnostics(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logger = logging.getLogger("machinate")
    monkeypatch.setenv("MACHI_LOG_LEVEL", "debug")
    target = project / ".machi/plans/bare/plan.md"
    target.parent.mkdir(parents=True)
    target.write_text("no frontmatter here")
    try:
        result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
        assert result.exit_code == 0
        assert "Missing YAML frontmatter in plans/bare/plan.md" in result.stderr
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)


def test_read_only_and_malformed_document(project: Path) -> None:
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


def test_help() -> None:
    result = runner.invoke(app, ["plan", "list", "--help"])
    assert result.exit_code == 0
    assert "--status" in result.stdout
    assert "--search-body" in result.stdout
    assert not result.stdout.startswith("{")


def test_help_does_not_prepare_project(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = Mock(side_effect=AssertionError("help must not prepare a project"))
    custom = create_cli(Dependencies(prepare_project=factory))
    monkeypatch.setenv("MACHI_INTERACTIVE", "invalid")
    for args in (["--help"], ["plan", "list", "--help"]):
        result = runner.invoke(custom, args)
        assert result.exit_code == 0, result.output
    factory.assert_not_called()


def test_repeated_invocations_reload_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom = create_cli()
    args = ["plan", "list", "-P", str(project)]
    first = runner.invoke(custom, args)
    assert first.exit_code == 0
    assert "No plans found." in first.stdout
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    second = runner.invoke(custom, args)
    assert second.exit_code == 0
    assert ListResult.model_validate_json(second.stdout).plans == []


@pytest.mark.parametrize("invalid", [["--limit"], ["--unknown"]])
@pytest.mark.parametrize("source", ["flag", "environment", "non_interactive"])
def test_parser_errors_use_json(
    invalid: list[str],
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = ["plan", "list"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    result = runner.invoke(create_cli(Dependencies(prepare_project=factory)), [*args, *invalid])
    assert result.exit_code == 2
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert invalid[0] in error.error
    factory.assert_not_called()


def test_parser_error_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["plan", "list", "--unknown", "--format=custom"])
    assert result.exit_code == 2
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[0], ErrorResult)


def test_parser_error_format_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "json")
    result = runner.invoke(app, ["plan", "list", "--format", "text", "--limit"])
    assert result.exit_code == 2
    assert result.stderr.startswith("Error:")
