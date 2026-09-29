import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from harness import cli, process_environment, seed

from machinate.cli.models import FindResult


@pytest.fixture
def find_project(project: Path) -> Path:
    seed.plan(project, "auth", body="auth")
    seed.plan(project, "billing", body="bills")
    seed.task(project, "auth", "login", body="intro\n\nkangaroo login flow\n\ntrailing\n")
    seed.context(project, "auth", "oauth", body="oauth notes")
    return project


def test_find_json_default_listing(find_project: Path) -> None:
    parsed = cli.json(FindResult, ["find", "-P", str(find_project), "--format", "json"])
    assert parsed.command == "find"
    assert parsed.project.name == "example"
    assert parsed.project.storage == find_project / ".machi"
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


def test_find_glob_option(find_project: Path) -> None:
    parsed = cli.json(
        FindResult,
        ["find", "-P", str(find_project), "--format", "json", "--glob", "plans/*/plan.md"],
    )
    assert parsed.globs == ["plans/*/plan.md"]
    assert [entry.path.as_posix() for entry in parsed.entries] == [
        "plans/auth/plan.md",
        "plans/billing/plan.md",
    ]


def test_find_limit_is_after_ranking(find_project: Path) -> None:
    parsed = cli.json(
        FindResult, ["find", "-P", str(find_project), "--format", "json", "login", "--limit", "1"]
    )
    assert [entry.path.as_posix() for entry in parsed.entries] == ["plans/auth/tasks/login.md"]


def test_find_missing_plan_errors(find_project: Path) -> None:
    error = cli.error(["find", "-P", str(find_project), "-p", "nope", "--format", "json"])
    assert error.command == "find"
    assert error.project is not None


def test_find_regex_without_flag_errors(find_project: Path) -> None:
    error = cli.error(["find", "-P", str(find_project), "path:/.*oauth.*/", "--format", "json"])
    assert error.command == "find"


def test_find_exact_flag_disables_fuzzy(find_project: Path) -> None:
    parsed = cli.json(
        FindResult, ["find", "-P", str(find_project), "--format", "json", "kang", "--exact"]
    )
    assert parsed.entries == []


def test_find_text_listing_omits_scores(find_project: Path) -> None:
    result = cli.run(["find", "-P", str(find_project), "--glob", "plans/*/plan.md"])
    assert result.exit_code == 0, result.stderr
    assert "plans/auth/plan.md" in result.stdout
    assert re.search(r"\d+\.\d", result.stdout) is None


def test_find_text_and_json_expose_the_same_entries(find_project: Path) -> None:
    parsed = cli.json(FindResult, ["find", "-P", str(find_project), "--format", "json", "kangaroo"])
    result = cli.run(["find", "-P", str(find_project), "kangaroo"])
    assert result.exit_code == 0, result.stderr
    assert parsed.entries
    for entry in parsed.entries:
        assert entry.path.as_posix() in result.stdout


def test_find_text_lists_paths_only(find_project: Path) -> None:
    result = cli.run(["find", "-P", str(find_project), "kangaroo"])
    assert result.exit_code == 0, result.stderr
    assert "plans/auth/tasks/login.md" in result.stdout
    assert "kangaroo login flow" not in result.stdout
    assert ":8" not in result.stdout


def test_find_json_entries_have_no_snippets(find_project: Path) -> None:
    parsed = cli.json(FindResult, ["find", "-P", str(find_project), "--format", "json", "kangaroo"])
    assert all("snippets" not in entry.model_dump() for entry in parsed.entries)


def test_find_via_installed_cli(find_project: Path) -> None:
    launcher = Path(sys.executable).with_name("machi")
    result = subprocess.run(  # noqa: S603 - checkout executable with fixed arguments
        [str(launcher), "find", "-P", str(find_project), "kangaroo", "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
        env=process_environment(),
    )
    assert result.returncode == 0, result.stderr
    parsed = FindResult.model_validate(json.loads(result.stdout))
    assert [entry.path.as_posix() for entry in parsed.entries] == ["plans/auth/tasks/login.md"]
