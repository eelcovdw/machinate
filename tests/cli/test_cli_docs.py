from pathlib import Path

from harness import JSON_DEPENDENCIES as JSON
from harness import cli


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
