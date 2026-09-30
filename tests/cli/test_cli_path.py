from pathlib import Path

import pytest
from harness import cli, seed_context, seed_doc, seed_plan, seed_task

from machinate.cli.models import PathResult


def seed(project: Path, resource: str, name: str) -> None:
    if resource == "task":
        seed_task(project, "auth", name)
    elif resource == "context":
        seed_context(project, "auth", name)
    else:
        seed_doc(project, name)


def document_args(resource: str, name: str) -> list[str]:
    if resource == "doc":
        return ["doc", "path", name]
    return [resource, "path", name, "-p", "auth"]


def directory_args(resource: str) -> list[str]:
    if resource == "doc":
        return ["doc", "path"]
    return [resource, "path", "-p", "auth"]


def test_plan_path_explicit(project: Path) -> None:
    seed_plan(project, "auth")
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


@pytest.mark.parametrize(
    ("resource", "name", "kind", "relative"),
    [
        ("task", "login", "task", ".machi/plans/auth/tasks/login.md"),
        ("context", "spec", "context", ".machi/plans/auth/context/spec.md"),
        ("doc", "guide", "doc", ".machi/docs/guide.md"),
    ],
)
def test_document_paths(project: Path, resource: str, name: str, kind: str, relative: str) -> None:
    seed_plan(project, "auth")
    seed(project, resource, name)
    parsed = cli.json(
        PathResult, [*document_args(resource, name), "-P", str(project), "--format", "json"]
    )
    assert parsed.kind == kind
    assert parsed.absolute_path == project / relative
    assert parsed.exists is None


@pytest.mark.parametrize(
    ("resource", "kind", "relative", "name"),
    [
        ("task", "task_directory", ".machi/plans/auth/tasks", "login"),
        ("context", "context_directory", ".machi/plans/auth/context", "spec"),
        ("doc", "doc_directory", ".machi/docs", "guide"),
    ],
)
def test_directory_paths(project: Path, resource: str, kind: str, relative: str, name: str) -> None:
    seed_plan(project, "auth")
    parsed = cli.json(
        PathResult, [*directory_args(resource), "-P", str(project), "--format", "json"]
    )
    assert parsed.kind == kind
    assert parsed.absolute_path == project / relative
    assert parsed.exists is False
    assert not (project / relative).exists()
    seed(project, resource, name)
    parsed = cli.json(
        PathResult, [*directory_args(resource), "-P", str(project), "--format", "json"]
    )
    assert parsed.exists is True


def test_plan_path_ignores_malformed_contents(project: Path) -> None:
    seed_plan(project, "auth")
    (project / ".machi/plans/auth/plan.md").write_text("---\nnot: [valid\n---\nbody\n")
    parsed = cli.json(
        PathResult, ["plan", "path", "-p", "auth", "-P", str(project), "--format", "json"]
    )
    assert parsed.absolute_path == project / ".machi/plans/auth/plan.md"
    assert parsed.exists is None


def test_path_missing_plan_reports_not_found(project: Path) -> None:
    error = cli.error(
        ["task", "path", "-p", "nope", "-P", str(project), "--format", "json"],
        code="not_found",
    )
    assert error.command == "task path"
