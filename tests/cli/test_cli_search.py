from pathlib import Path

from harness import cli, seed_context, seed_doc, seed_plan, seed_task

from machinate.cli.models import SearchResult


def find_project(project: Path) -> Path:
    seed_plan(project, "auth", body="auth")
    seed_plan(project, "billing", body="bills")
    seed_task(project, "auth", "login", body="intro\n\nkangaroo login flow\n\ntrailing\n")
    seed_context(project, "auth", "oauth", body="oauth notes")
    seed_doc(project, "guide", body="kangaroo guide")
    return project


def test_search_json_default_listing(project: Path) -> None:
    find_project(project)
    parsed = cli.json(SearchResult, ["search", "-P", str(project), "--format", "json"])
    assert parsed.command == "search"
    assert parsed.project.name == "example"
    assert parsed.project.store_directory == project / ".machi"
    assert parsed.plan_name is None
    assert parsed.query is None
    assert parsed.globs == ["**/*.md"]
    assert [entry.path.as_posix() for entry in parsed.matches] == [
        "docs/guide.md",
        "plans/auth/context/oauth.md",
        "plans/auth/plan.md",
        "plans/auth/tasks/login.md",
        "plans/billing/plan.md",
    ]
    assert all(entry.score is None for entry in parsed.matches)
    login = next(entry for entry in parsed.matches if entry.name == "login")
    assert (login.kind, login.plan_name, login.name) == ("task", "auth", "login")


def test_search_glob_option(project: Path) -> None:
    find_project(project)
    parsed = cli.json(
        SearchResult,
        ["search", "-P", str(project), "--format", "json", "--glob", "plans/*/plan.md"],
    )
    assert parsed.globs == ["plans/*/plan.md"]
    assert [entry.path.as_posix() for entry in parsed.matches] == [
        "plans/auth/plan.md",
        "plans/billing/plan.md",
    ]


def test_search_text_lists_paths(project: Path) -> None:
    find_project(project)
    result = cli.run(["search", "-P", str(project), "--format", "text", "login"])
    assert result.exit_code == 0, result.output
    assert "plans/auth/tasks/login.md" in result.stdout


def test_search_exact_flag_disables_fuzzy(project: Path) -> None:
    find_project(project)
    parsed = cli.json(
        SearchResult, ["search", "-P", str(project), "--format", "json", "kang", "--exact"]
    )
    assert parsed.matches == []


def test_search_regex_without_flag_errors(project: Path) -> None:
    find_project(project)
    error = cli.error(
        ["search", "-P", str(project), "--format", "json", "path:/conf.*/"],
        code="search_query",
    )
    assert error.command == "search"
