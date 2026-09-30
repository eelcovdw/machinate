from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from harness import DEFAULT_DEPENDENCIES, DEFAULT_SETTINGS, make_settings
from typer.testing import CliRunner

from machinate.cli.cli import build_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult, PlanListResult
from machinate.cli.project_setup import open_project
from machinate.models.documents import ParsedDocument, PlanMetadata
from machinate.models.operations import PlanQuery
from machinate.storage import (
    DocumentStore,
    Layout,
    ProjectState,
    ProjectStateStore,
)

runner = CliRunner()
app = build_cli(DEFAULT_DEPENDENCIES)


def populate(project: Path) -> None:
    store = DocumentStore(project / ".machi")
    for name, status in (("beta", "done"), ("alpha", "active")):
        store.create(
            Layout().plan_path(name),
            ParsedDocument(
                metadata=PlanMetadata.model_validate(
                    {
                        "created_at": datetime(2026, 9, 22, tzinfo=UTC),
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
        parsed = PlanListResult.model_validate_json(result.stdout)
        assert parsed.project.directory == project
        assert parsed.project.store_directory == project / ".machi"
        assert parsed.project.name == "example"
        assert [plan.name for plan in parsed.plans] == ["alpha", "beta"]


def test_list_marks_current_plan(project: Path) -> None:
    populate(project)
    ProjectStateStore(project / ".machi/machinate.toml").write(
        ProjectState(project_name="example", current_plan="alpha")
    )
    parsed = PlanListResult.model_validate_json(
        runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"]).stdout
    )
    assert parsed.current_plan == "alpha"
    text = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "text"]).stdout
    assert "* alpha" in text
    assert "* beta" not in text


def test_nearest_project(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = project / "nested"
    ProjectStateStore(nested / ".machi/machinate.toml").write(ProjectState(project_name="inner"))
    monkeypatch.chdir(nested)
    result = runner.invoke(app, ["plan", "list", "--format", "json"])
    assert PlanListResult.model_validate_json(result.stdout).project.name == "inner"


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
        parsed = PlanListResult.model_validate_json(result.stdout)
        assert parsed.project.name == "linked"
        assert parsed.project.store_directory == linked / ".machi"


def test_query_delegation(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    populate(project)
    application = open_project(project)
    summaries = application.plans.list_records()[::-1]
    listing = Mock(return_value=summaries)
    monkeypatch.setattr(application.plans, "list_records", listing)
    factory = Mock(return_value=application)
    result = runner.invoke(
        build_cli(Dependencies(settings=DEFAULT_SETTINGS, open_project=factory)),
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
            "last_activity_at",
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
            sort="last_activity_at",
            descending=True,
            limit=1,
        )
    )
    parsed = PlanListResult.model_validate_json(result.stdout)
    assert [plan.model_dump(mode="json") for plan in parsed.plans] == [
        plan.model_dump(mode="json") for plan in summaries
    ]


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
    assert [p.name for p in PlanListResult.model_validate_json(result.stdout).plans] == ["beta"]


@pytest.mark.parametrize("populated", [False, True])
@pytest.mark.parametrize("format_name", ["text", "json"])
def test_output(project: Path, populated: bool, format_name: str) -> None:
    if populated:
        populate(project)
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", format_name])
    assert result.exit_code == 0, result.output
    if format_name == "json":
        assert len(PlanListResult.model_validate_json(result.stdout).plans) == (
            2 if populated else 0
        )
    else:
        assert "example" in result.stdout


@pytest.mark.parametrize(
    ("settings_kwargs", "flag", "expected"),
    [
        ({}, None, "text"),
        ({"ai_agent": "test-agent"}, None, "json"),
        ({"ai_agent": None}, None, "text"),
        ({"ai_agent": "test-agent", "format": "text"}, None, "text"),
        ({"format": "json"}, None, "json"),
        ({"ai_agent": "test-agent", "format": "json"}, "text", "text"),
    ],
)
def test_format_precedence(
    project: Path,
    settings_kwargs: dict[str, object],
    flag: str | None,
    expected: str,
) -> None:
    format_value = settings_kwargs.get("format")
    ai_agent = settings_kwargs.get("ai_agent")
    dependencies = Dependencies(
        settings=make_settings(
            ai_agent=ai_agent if isinstance(ai_agent, str) else None,
            format_name=format_value if isinstance(format_value, str) else None,
        )
    )
    args = ["plan", "list", "-P", str(project)]
    if flag is not None:
        args.extend(["--format", flag])
    result = runner.invoke(build_cli(dependencies), args)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{") == (expected == "json")


@pytest.mark.parametrize(
    ("args", "exit_code"),
    [
        (["--format", "human"], 2),
        (["--status", "bad"], 2),
        (["--sort", "bad"], 2),
        (["--limit", "0"], 2),
        (["--limit", "abc"], 2),
    ],
)
def test_invalid_options(project: Path, args: list[str], exit_code: int) -> None:
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json", *args])
    assert result.exit_code == exit_code, result.output


def test_read_only_and_malformed_document(project: Path) -> None:
    open_project(project).plans.project_state_store.write(
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
    assert open_project(project).plans.project_state_store.read().current_plan == "dangling"
    (project / ".machi/plans/alpha/plan.md").write_text("---\nsummary: missing date\n---\n")
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 1
    error = ErrorResult.model_validate_json(result.stderr)
    assert "alpha/plan.md" in error.error
    assert error.project is not None
    assert error.project.directory == project


@pytest.mark.parametrize("invalid", [["--limit"], ["--unknown"]])
@pytest.mark.parametrize("source", ["flag", "environment", "agent"])
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
        settings = make_settings(ai_agent="test-agent")
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    dependencies = Dependencies(settings=settings, open_project=factory)
    result = runner.invoke(build_cli(dependencies), [*args, *invalid])
    assert result.exit_code == 2
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert invalid[0] in error.error
    factory.assert_not_called()


def test_parser_error_format_override() -> None:
    dependencies = Dependencies(settings=make_settings(format_name="json"))
    result = runner.invoke(build_cli(dependencies), ["plan", "list", "--format", "text", "--limit"])
    assert result.exit_code == 2
    assert not result.stderr.startswith("{")


def test_group_parser_errors_use_json() -> None:
    """C5: group failures follow the same formatting policy as leaf commands."""
    factory = Mock(side_effect=AssertionError("parse failure must not prepare a project"))
    custom = build_cli(
        Dependencies(settings=make_settings(ai_agent="test-agent"), open_project=factory)
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
    result = runner.invoke(build_cli(dependencies), ["task", "oops"])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert not result.stderr.startswith("{")


def test_group_help_still_prints() -> None:
    """C5 must not swallow the no-args help path for groups."""
    dependencies = Dependencies(settings=make_settings(format_name="json"))
    result = runner.invoke(build_cli(dependencies), ["task"])
    assert result.exit_code == 2
    # Click prints the no-args help for a group to stderr; the point is it is not swallowed.
    assert result.stderr
