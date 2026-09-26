from pathlib import Path
from typing import ClassVar, get_args
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import JsonSchemaValue
from typer.testing import CliRunner

from machinate.cli.cli import app, create_cli
from machinate.cli.commands.catalog import COMMANDS
from machinate.cli.commands.schema import SCHEMA_RESULTS
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import CommandResult, ErrorResult

runner = CliRunner()


class _Node(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    ref: str | None = Field(default=None, alias="$ref")
    commands: dict[str, "_Node"] | None = None  # noqa: UP037 - forward ref needed by Pydantic


class _Bundle(BaseModel):
    version: str
    commands: dict[str, _Node]
    error: _Node
    defs: dict[str, JsonSchemaValue] = Field(alias="$defs")


class _GroupSchema(BaseModel):
    commands: dict[str, _Node]
    defs: dict[str, JsonSchemaValue] = Field(alias="$defs")


def _flatten(nodes: dict[str, _Node], prefix: str = "") -> dict[str, str]:
    refs: dict[str, str] = {}
    for name, node in nodes.items():
        if node.commands is not None:
            refs.update(_flatten(node.commands, prefix=f"{prefix}{name} "))
        else:
            assert node.ref is not None
            refs[f"{prefix}{name}"] = node.ref
    return refs


class _CommandSchema(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    type: str
    properties: dict[str, JsonSchemaValue]
    required: list[str] = Field(default_factory=list)
    defs: dict[str, JsonSchemaValue] = Field(default_factory=dict, alias="$defs")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_INTERACTIVE"):
        monkeypatch.delenv(name, raising=False)


def test_schema_lists_all_commands() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    bundle = _Bundle.model_validate_json(result.stdout)
    assert set(bundle.commands) == {spec.name for spec in COMMANDS}
    assert _flatten(bundle.commands) == {
        path: f"#/$defs/{model.__name__}" for path, model in SCHEMA_RESULTS.items()
    }
    assert bundle.error.ref == "#/$defs/ErrorResult"
    assert bundle.version
    for model in [*SCHEMA_RESULTS.values(), ErrorResult]:
        assert model.__name__ in bundle.defs


def test_catalog_is_the_single_source_of_truth() -> None:
    cli = create_cli()
    registered = {command.name for command in cli.registered_commands}
    groups = {group.name for group in cli.registered_groups}
    assert registered == {spec.name for spec in COMMANDS if not spec.children} | {"schema"}
    assert groups == {spec.name for spec in COMMANDS if spec.children}


def test_schema_map_covers_the_command_result_union() -> None:
    union = set(get_args(CommandResult.__value__))  # pyright: ignore[reportAny]
    assert set(SCHEMA_RESULTS.values()) | {ErrorResult} == union


def test_schema_refs_resolve() -> None:
    bundle = _Bundle.model_validate_json(runner.invoke(app, ["schema"]).stdout)
    refs = [*_flatten(bundle.commands).values(), bundle.error.ref]
    for ref in refs:
        assert ref is not None
        assert ref.rsplit("/", maxsplit=1)[-1] in bundle.defs


def test_schema_for_command() -> None:
    schema = _CommandSchema.model_validate_json(
        runner.invoke(app, ["schema", "plan", "show"]).stdout
    )
    assert schema.type == "object"
    assert {"command", "project", "plan"} <= set(schema.properties)
    assert {"project", "plan"} <= set(schema.required)
    assert "ShowResult" not in schema.defs


def test_schema_for_plan_group() -> None:
    group = _GroupSchema.model_validate_json(runner.invoke(app, ["schema", "plan"]).stdout)
    assert set(group.commands) == {"add", "info", "list", "path", "set", "show", "status"}
    assert group.commands["info"].ref == "#/$defs/PlanInfoResult"
    assert group.commands["show"].ref == "#/$defs/ShowResult"
    assert "PlanInfoResult" in group.defs


def test_schema_for_group() -> None:
    group = _GroupSchema.model_validate_json(runner.invoke(app, ["schema", "task"]).stdout)
    assert set(group.commands) == {"add", "info", "list", "path", "show", "status"}
    assert group.commands["add"].ref == "#/$defs/TaskAddResult"
    assert group.commands["info"].ref == "#/$defs/TaskInfoResult"
    assert group.commands["list"].ref == "#/$defs/TaskListResult"
    assert group.commands["path"].ref == "#/$defs/PathResult"
    assert group.commands["show"].ref == "#/$defs/TaskShowResult"
    assert group.commands["status"].ref == "#/$defs/TaskStatusResult"
    assert "TaskAddResult" in group.defs
    assert "TaskInfoResult" in group.defs
    assert "TaskListResult" in group.defs
    assert "TaskShowResult" in group.defs
    assert "TaskStatusResult" in group.defs


def test_schema_for_nested_command() -> None:
    schema = _CommandSchema.model_validate_json(
        runner.invoke(app, ["schema", "task", "add"]).stdout
    )
    assert schema.type == "object"
    assert {"command", "project", "plan", "tasks"} <= set(schema.properties)


def test_schema_unknown_nested_command() -> None:
    result = runner.invoke(app, ["schema", "task", "nope"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "schema"
    assert "Unknown schema 'nope'" in error.error


def test_schema_error_envelope() -> None:
    schema = _CommandSchema.model_validate_json(runner.invoke(app, ["schema", "error"]).stdout)
    assert {"command", "error", "project"} <= set(schema.properties)


def test_schema_unknown_command() -> None:
    result = runner.invoke(app, ["schema", "nope"])
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "schema"
    assert "Unknown schema 'nope'" in error.error
    assert "plan" in error.error


def test_schema_needs_no_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    assert _Bundle.model_validate_json(result.stdout).version


def test_schema_help() -> None:
    result = runner.invoke(app, ["schema", "--help"])
    assert result.exit_code == 0
    assert "result schema to print" in result.stdout
    assert not result.stdout.startswith("{")


def test_schema_parser_errors_follow_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = Mock(side_effect=AssertionError("schema must not prepare a project"))
    dependencies = Dependencies(prepare_project=factory)
    cli = create_cli(dependencies)

    text = runner.invoke(cli, ["schema", "--unknown"])
    assert text.exit_code == 2
    assert text.stdout == ""
    assert "--unknown" in text.stderr

    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    structured = runner.invoke(cli, ["schema", "--unknown"])
    assert structured.exit_code == 2
    assert structured.stdout == ""
    error = ErrorResult.model_validate_json(structured.stderr)
    assert error.command == "schema"
    assert "--unknown" in error.error

    factory.assert_not_called()
