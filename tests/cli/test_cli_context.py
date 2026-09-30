import json
from pathlib import Path
from typing import cast

import pytest
from harness import JSON_DEPENDENCIES as JSON
from harness import cli, seed_context, seed_plan


@pytest.fixture
def auth_project(project: Path) -> Path:
    seed_plan(project, "auth")
    seed_context(project, "auth", "spec")
    return project


@pytest.mark.parametrize(
    ("args", "command"),
    [
        (["context", "add", "notes"], "context add"),
        (["context", "list"], "context list"),
        (["context", "show", "spec"], "context show"),
        (["context", "info", "spec"], "context info"),
        (["context", "update", "spec", "--summary", "New"], "context update"),
    ],
)
def test_context_subcommands_run(auth_project: Path, args: list[str], command: str) -> None:
    result = cli.run([*args, "-p", "auth", "-P", str(auth_project)], dependencies=JSON)
    assert result.exit_code == 0, result.output + result.stderr
    payload = cast("dict[str, object]", json.loads(result.stdout))
    assert payload["command"] == command


def test_context_list_invalid_limit(auth_project: Path) -> None:
    error = cli.error(
        ["context", "list", "-p", "auth", "-P", str(auth_project), "--limit", "0"],
        code="input",
        dependencies=JSON,
        expect=2,
    )
    assert error.command == "context list"
