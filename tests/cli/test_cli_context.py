import json
from pathlib import Path
from typing import cast

import pytest
from harness import AUTOMATION_DEPENDENCIES as AUTOMATION
from harness import DEFAULT_DEPENDENCIES as TEXT
from harness import JSON_DEPENDENCIES as JSON
from harness import cli, read_state, seed

from machinate.cli.models import (
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ContextUpdateResult,
)
from machinate.cli.project_setup import prepare_project

CONTEXT_INVOCATIONS = {
    "add": ["context", "add", "spec"],
    "list": ["context", "list"],
    "show": ["context", "show", "spec"],
    "info": ["context", "info", "spec"],
    "update": ["context", "update", "spec", "--summary", "x"],
}


@pytest.mark.parametrize("command", list(CONTEXT_INVOCATIONS))
def test_context_plan_resolution(project: Path, command: str) -> None:
    """Every context subcommand shares select_plan, so resolution is tested once per command."""
    args = CONTEXT_INVOCATIONS[command]
    unknown = cli.error([*args, "-p", "nope", "-P", str(project)], dependencies=JSON)
    assert unknown.command == f"context {command}"

    unselected = cli.error([*args, "-P", str(project)], dependencies=JSON)
    assert unselected.command == f"context {command}"

    automated = cli.error([*args, "-P", str(project)], dependencies=AUTOMATION)
    assert automated.command == f"context {command}"


def test_context_add_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        ContextAddResult,
        ["context", "add", "spec", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert parsed.project.name == "example"
    assert parsed.project.directory == project
    assert parsed.project.storage == project / ".machi"
    assert parsed.plan == "auth"
    context = parsed.contexts[0]
    assert context.name == "spec"
    assert context.path.as_posix() == "plans/auth/context/spec.md"
    assert context.document.metadata.created.tzinfo is not None
    assert context.document.metadata.summary is None
    assert context.document.body == ""
    assert (project / ".machi/plans/auth/context/spec.md").is_file()
    assert read_state(project).current_plan is None


def test_context_add_current_plan(project: Path) -> None:
    seed.plan(project, "auth")
    prepare_project(project).plans.set_current("auth")
    parsed = cli.json(
        ContextAddResult, ["context", "add", "spec", "-P", str(project)], dependencies=JSON
    )
    assert parsed.plan == "auth"


def test_context_add_multiple(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        ContextAddResult,
        ["context", "add", "spec", "notes", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert [context.name for context in parsed.contexts] == ["spec", "notes"]


def test_context_add_batch_partial_success(project: Path) -> None:
    """C2: an existing name must not abort the batch or swallow later names."""
    seed.plan(project, "auth")
    seed.context(project, "auth", "existing")
    parsed = cli.json(
        ContextAddResult,
        [
            "context",
            "add",
            "new",
            "existing",
            "later",
            "../bad",
            "-p",
            "auth",
            "-P",
            str(project),
        ],
        dependencies=JSON,
        expect=1,
    )
    assert [context.name for context in parsed.contexts] == ["new", "later"]
    assert [error.name for error in parsed.errors] == ["existing", "../bad"]
    assert (project / ".machi/plans/auth/context/new.md").exists()
    assert (project / ".machi/plans/auth/context/later.md").exists()
    assert (project / ".machi/plans/auth/context/existing.md").exists()  # Not overwritten.


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_context_add_output(project: Path, format_name: str) -> None:
    seed.plan(project, "auth")
    args = ["context", "add", "spec", "-p", "auth", "-P", str(project)]
    if format_name == "json":
        parsed = cli.json(ContextAddResult, args, dependencies=JSON)
        assert parsed.contexts[0].name == "spec"
    else:
        result = cli.run(args, dependencies=TEXT)
        assert result.exit_code == 0, result.output
        assert "spec" in result.stdout


def test_context_list_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec")
    seed.context(project, "auth", "notes")
    parsed = cli.json(
        ContextListResult,
        ["context", "list", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert parsed.project.name == "example"
    assert parsed.plan == "auth"
    assert [context.name for context in parsed.contexts] == ["notes", "spec"]
    assert read_state(project).current_plan is None


def test_context_list_empty(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        ContextListResult,
        ["context", "list", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert parsed.contexts == []


def test_context_list_invalid_limit(project: Path) -> None:
    seed.plan(project, "auth")
    error = cli.error(
        ["context", "list", "-p", "auth", "-P", str(project), "--limit", "0"],
        dependencies=JSON,
    )
    assert error.command == "context list"


def test_context_list_text_output(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec", summary="The spec")
    result = cli.run(["context", "list", "-p", "auth", "-P", str(project)], dependencies=TEXT)
    assert result.exit_code == 0, result.output
    assert "spec" in result.stdout


def test_context_show_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec", body="# Spec\n\nDetails.\n")
    parsed = cli.json(
        ContextShowResult,
        ["context", "show", "spec", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert parsed.project.name == "example"
    assert parsed.plan == "auth"
    assert parsed.context.name == "spec"
    assert parsed.context.path.as_posix() == "plans/auth/context/spec.md"
    assert parsed.context.document.get_or_derive_summary() == "Details."
    assert parsed.context.document.body == "# Spec\n\nDetails.\n"
    assert parsed.context.document.metadata.created.tzinfo is not None


def test_context_show_unknown_context(project: Path) -> None:
    seed.plan(project, "auth")
    error = cli.error(
        ["context", "show", "missing", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert error.command == "context show"


def test_context_show_text_output(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec", summary="The spec", body="# Spec\n\nDetails.")
    result = cli.run(
        ["context", "show", "spec", "-p", "auth", "-P", str(project)], dependencies=TEXT
    )
    assert result.exit_code == 0, result.output
    assert "spec" in result.stdout


def test_context_info_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec", body="# Spec\n\nDetails.\n")
    parsed = cli.json(
        ContextInfoResult,
        ["context", "info", "spec", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert parsed.project.name == "example"
    assert parsed.plan == "auth"
    assert parsed.context.name == "spec"
    assert parsed.context.path.as_posix() == "plans/auth/context/spec.md"
    assert parsed.context.summary == "Details."
    assert parsed.context.last_activity_at.tzinfo is not None


def test_context_info_omits_body(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec", summary="The spec", body="# Spec\n\nDetails.\n")
    result = cli.run(
        ["context", "info", "spec", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert result.exit_code == 0, result.output
    payload = cast("dict[str, object]", json.loads(result.stdout)["context"])
    assert "document" not in payload
    assert "body" not in payload


def test_context_info_unknown_context(project: Path) -> None:
    seed.plan(project, "auth")
    error = cli.error(
        ["context", "info", "missing", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert error.command == "context info"


def test_context_info_text_output(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec", summary="The spec", body="# Spec\n\nDetails.")
    result = cli.run(
        ["context", "info", "spec", "-p", "auth", "-P", str(project)], dependencies=TEXT
    )
    assert result.exit_code == 0, result.output
    assert "spec" in result.stdout


def test_context_update_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec")
    parsed = cli.json(
        ContextUpdateResult,
        ["context", "update", "spec", "--summary", "New", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert parsed.plan == "auth"
    assert parsed.context.name == "spec"
    assert parsed.context.document.metadata.summary == "New"


def test_context_update_unknown_context(project: Path) -> None:
    seed.plan(project, "auth")
    error = cli.error(
        ["context", "update", "missing", "--summary", "x", "-p", "auth", "-P", str(project)],
        dependencies=JSON,
    )
    assert error.command == "context update"


def test_context_update_text_output(project: Path) -> None:
    seed.plan(project, "auth")
    seed.context(project, "auth", "spec")
    result = cli.run(
        ["context", "update", "spec", "--summary", "New", "-p", "auth", "-P", str(project)],
        dependencies=TEXT,
    )
    assert result.exit_code == 0, result.output
    assert "spec" in result.stdout
