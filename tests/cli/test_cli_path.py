from pathlib import Path

from harness import cli, read_state, seed

from machinate.cli.models import PathResult
from machinate.cli.project_setup import open_project


def test_plan_path_explicit(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        PathResult, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.command == "plan path"
    assert parsed.project.name == "example"
    assert parsed.project.store_directory == project / ".machi"
    assert parsed.plan_name == "auth"
    assert parsed.absolute_path == project / ".machi/plans/auth/plan.md"
    assert parsed.kind == "plan"
    assert parsed.exists is None
    assert read_state(project).current_plan is None


def test_plan_path_text_smoke(project: Path) -> None:
    seed.plan(project, "auth")
    result = cli.run(["plan", "path", "-p", "auth", "-P", str(project)])
    assert result.exit_code == 0
    assert result.stdout == f"{project / '.machi/plans/auth/plan.md'}\n"


def test_plan_path_current_plan(project: Path) -> None:
    seed.plan(project, "auth")
    seed.plan(project, "billing")
    open_project(project).plans.select_plan("auth")
    parsed = cli.json(PathResult, ["plan", "path", "-P", str(project), "--format", "json"])
    assert parsed.plan_name == "auth"


def test_plan_path_does_not_change_selection(project: Path) -> None:
    seed.plan(project, "auth")
    seed.plan(project, "billing")
    open_project(project).plans.select_plan("auth")
    cli.json(PathResult, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"])
    assert read_state(project).current_plan == "auth"


def test_plan_path_no_current_plan(project: Path) -> None:
    error = cli.error(["plan", "path", "-P", str(project), "--format", "json"])
    assert error.command == "plan path"


def test_task_path_document(project: Path) -> None:
    seed.plan(project, "auth")
    seed.task(project, "auth", "login")
    parsed = cli.json(
        PathResult,
        ["task", "path", "login", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert parsed.command == "task path"
    assert parsed.kind == "task"
    assert parsed.absolute_path == project / ".machi/plans/auth/tasks/login.md"
    assert parsed.exists is None


def test_task_path_directory_absent(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        PathResult, ["task", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.kind == "task_directory"
    assert parsed.absolute_path == project / ".machi/plans/auth/tasks"
    assert parsed.exists is False


def test_task_path_directory_exists(project: Path) -> None:
    seed.plan(project, "auth")
    seed.task(project, "auth", "login")
    parsed = cli.json(
        PathResult, ["task", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.kind == "task_directory"
    assert parsed.exists is True


def test_task_path_directory_never_creates(project: Path) -> None:
    seed.plan(project, "auth")
    cli.json(PathResult, ["task", "path", "-p", "auth", "-P", str(project), "--format", "json"])
    assert not (project / ".machi/plans/auth/tasks").exists()


def test_task_path_directory_missing_plan_reports_not_found(project: Path) -> None:
    error = cli.error(["task", "path", "-p", "nope", "-P", str(project), "--format", "json"])
    assert error.command == "task path"
    assert error.code == "not_found"


def test_context_path_document(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec")
    parsed = cli.json(
        PathResult,
        ["context", "path", "spec", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert parsed.command == "context path"
    assert parsed.kind == "context"
    assert parsed.absolute_path == project / ".machi/plans/auth/context/spec.md"
    assert parsed.exists is None


def test_context_path_directory_absent(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        PathResult,
        ["context", "path", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert parsed.kind == "context_directory"
    assert parsed.absolute_path == project / ".machi/plans/auth/context"
    assert parsed.exists is False


def test_context_path_directory_exists(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec")
    parsed = cli.json(
        PathResult,
        ["context", "path", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert parsed.exists is True


def test_plan_path_ignores_malformed_contents(project: Path) -> None:
    seed.plan(project, "auth")
    (project / ".machi/plans/auth/plan.md").write_text("---\nnot: [valid\n---\nbody\n")
    parsed = cli.json(
        PathResult, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.absolute_path == project / ".machi/plans/auth/plan.md"
    assert parsed.exists is None


def test_task_path_ignores_malformed_contents(project: Path) -> None:
    seed.plan(project, "auth")
    seed.task(project, "auth", "login")
    target = project / ".machi/plans/auth/tasks/login.md"
    target.write_text("---\nnot: [valid\n---\nbody\n")
    parsed = cli.json(
        PathResult,
        ["task", "path", "login", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert parsed.absolute_path == target
    assert parsed.exists is None


def test_context_path_ignores_malformed_contents(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec")
    target = project / ".machi/plans/auth/context/spec.md"
    target.write_text("---\nnot: [valid\n---\nbody\n")
    parsed = cli.json(
        PathResult,
        ["context", "path", "spec", "-p", "auth", "-P", str(project), "--format", "json"],
    )
    assert parsed.absolute_path == target
    assert parsed.exists is None
