import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app
from machinate.cli.models import ErrorResult, FindResult
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentStore,
    Layout,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
    TaskMetadata,
)

runner = CliRunner()
_NOW = datetime(2026, 9, 22, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_LOG_LEVEL", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    ProjectStateStore(root / ".machi/machinate.toml").write(
        ProjectState(project_name="example", current_plan=None)
    )
    store = DocumentStore(root / ".machi")
    layout = Layout()
    store.create(layout.plan("auth"), Document(metadata=PlanMetadata(created=_NOW), body="auth"))
    store.create(
        layout.plan("billing"), Document(metadata=PlanMetadata(created=_NOW), body="bills")
    )
    store.create(
        layout.task("auth", "login"),
        Document(
            metadata=TaskMetadata(created=_NOW), body="intro\n\nkangaroo login flow\n\ntrailing\n"
        ),
    )
    store.create(
        layout.context("auth", "oauth"),
        Document(metadata=ContextMetadata(created=_NOW), body="oauth notes"),
    )
    return root


def invoke(project: Path, *args: str) -> FindResult:
    result = runner.invoke(app, ["find", "-P", str(project), "--format", "json", *args])
    assert result.exit_code == 0, result.stderr
    return FindResult.model_validate(json.loads(result.stdout))


def invoke_text(project: Path, *args: str) -> str:
    result = runner.invoke(app, ["find", "-P", str(project), *args])
    assert result.exit_code == 0, result.stderr
    return result.stdout


def test_find_json_default_listing(project: Path) -> None:
    parsed = invoke(project)
    assert parsed.command == "find"
    assert parsed.project.name == "example"
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan is None
    assert parsed.query is None
    assert parsed.globs == ["**/*.md"]
    assert [entry.path.as_posix() for entry in parsed.entries] == [
        "plans/auth/context/oauth.md",
        "plans/auth/plan.md",
        "plans/auth/tasks/login.md",
        "plans/billing/plan.md",
    ]
    assert all(entry.score is None for entry in parsed.entries)
    login = next(entry for entry in parsed.entries if entry.name == "login")
    assert (login.kind, login.plan, login.name) == ("task", "auth", "login")


def test_find_query_scores_and_filters(project: Path) -> None:
    parsed = invoke(project, "kangaroo")
    assert parsed.query == "kangaroo"
    assert [entry.path.as_posix() for entry in parsed.entries] == ["plans/auth/tasks/login.md"]
    assert parsed.entries[0].score is not None


def test_find_short_query_matches_tokens(project: Path) -> None:
    parsed = invoke(project, "kang")
    assert [entry.path.as_posix() for entry in parsed.entries] == ["plans/auth/tasks/login.md"]


def test_find_glob_option(project: Path) -> None:
    parsed = invoke(project, "--glob", "plans/*/plan.md")
    assert parsed.globs == ["plans/*/plan.md"]
    assert [entry.path.as_posix() for entry in parsed.entries] == [
        "plans/auth/plan.md",
        "plans/billing/plan.md",
    ]


def test_find_plan_scope(project: Path) -> None:
    parsed = invoke(project, "-p", "auth")
    assert parsed.plan == "auth"
    assert all(entry.plan == "auth" for entry in parsed.entries)
    assert all(entry.path.as_posix().startswith("plans/auth/") for entry in parsed.entries)


def test_find_limit_is_after_ranking(project: Path) -> None:
    parsed = invoke(project, "login", "--limit", "1")
    assert [entry.path.as_posix() for entry in parsed.entries] == ["plans/auth/tasks/login.md"]


def test_find_missing_plan_errors(project: Path) -> None:
    result = runner.invoke(app, ["find", "-P", str(project), "-p", "nope", "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "find"
    assert error.project is not None


def test_find_regex_without_flag_errors(project: Path) -> None:
    result = runner.invoke(
        app, ["find", "-P", str(project), "path:/.*oauth.*/", "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).command == "find"


def test_find_regex_flag_allows_field_scoped_regex(project: Path) -> None:
    parsed = invoke(project, "path:/.*oauth.*/", "--regex")
    assert [entry.path.as_posix() for entry in parsed.entries] == ["plans/auth/context/oauth.md"]


def test_find_exact_flag_disables_fuzzy(project: Path) -> None:
    parsed = invoke(project, "kang", "--exact")
    assert parsed.entries == []


def test_find_text_ranked_shows_score_and_owner(project: Path) -> None:
    parsed = invoke(project, "kangaroo")
    score = parsed.entries[0].score
    assert score is not None
    output = invoke_text(project, "kangaroo")
    assert f"{score:.1f}" in output
    assert "plans/auth/tasks/login.md" in output
    assert "[task auth]" in output


def test_find_text_listing_omits_scores(project: Path) -> None:
    output = invoke_text(project, "--glob", "plans/*/plan.md")
    assert "plans/auth/plan.md" in output
    assert "[plan auth]" in output
    assert re.search(r"\d+\.\d", output) is None


def test_find_text_and_json_expose_the_same_entries(project: Path) -> None:
    parsed = invoke(project, "kangaroo")
    output = invoke_text(project, "kangaroo")
    assert parsed.entries
    for entry in parsed.entries:
        assert entry.path.as_posix() in output


def test_find_text_lists_paths_only(project: Path) -> None:
    output = invoke_text(project, "kangaroo")
    assert "plans/auth/tasks/login.md" in output
    assert "kangaroo login flow" not in output
    assert ":8" not in output


def test_find_json_entries_have_no_snippets(project: Path) -> None:
    parsed = invoke(project, "kangaroo")
    assert all("snippets" not in entry.model_dump() for entry in parsed.entries)


def test_find_prefix_and_typo_queries(project: Path) -> None:
    for query in ("kang", "kanguroo"):
        parsed = invoke(project, query)
        assert parsed.entries, query


def test_find_via_installed_cli(project: Path) -> None:
    launcher = Path(sys.executable).with_name("machi")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_LOG_LEVEL", "MACHI_AGENT"}
    }
    result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "find", "-P", str(project), "kangaroo", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    parsed = FindResult.model_validate(json.loads(result.stdout))
    assert [entry.path.as_posix() for entry in parsed.entries] == ["plans/auth/tasks/login.md"]
