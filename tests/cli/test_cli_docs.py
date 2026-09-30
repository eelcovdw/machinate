from pathlib import Path

from harness import JSON_DEPENDENCIES as JSON
from harness import cli, seed

from machinate.cli.models import PathResult


def test_doc_group_runs_without_a_plan(project: Path) -> None:
    """Every doc subcommand works with no plan selected and no -p."""
    invocations = [
        ["doc", "add", "spec"],
        ["doc", "list"],
        ["doc", "show", "spec"],
        ["doc", "info", "spec"],
        ["doc", "path", "spec"],
        ["doc", "update", "spec", "--summary", "x"],
    ]
    for args in invocations:
        result = cli.run([*args, "-P", str(project)], dependencies=JSON)
        assert result.exit_code == 0, (args, result.output + result.stderr)


def test_doc_path_reports_project_paths(project: Path) -> None:
    seed.doc(project, "spec")

    folder = cli.json(
        PathResult,
        ["doc", "path", "-P", str(project)],
        dependencies=JSON,
    )
    assert folder.kind == "doc_directory"
    assert folder.plan_name is None
    assert folder.absolute_path == project / ".machi/docs"

    target = cli.json(
        PathResult,
        ["doc", "path", "spec", "-P", str(project)],
        dependencies=JSON,
    )
    assert target.kind == "doc"
    assert target.plan_name is None
    assert target.absolute_path == project / ".machi/docs/spec.md"
