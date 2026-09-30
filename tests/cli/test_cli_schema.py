from pathlib import Path
from typing import ClassVar, get_args

import pytest
from harness import DEFAULT_DEPENDENCIES
from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import JsonSchemaValue
from typer.testing import CliRunner

from machinate.cli.cli import build_cli
from machinate.cli.commands.catalog import ALIASES, COMMANDS, CommandGroup, leaves
from machinate.cli.commands.schema import _result_models
from machinate.cli.models import CommandResult, ErrorResult

runner = CliRunner()
app = build_cli(DEFAULT_DEPENDENCIES)


class _Node(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    ref: str | None = Field(default=None, alias="$ref")
    commands: dict[str, "_Node"] | None = None  # noqa: UP037 - forward ref needed by Pydantic


class _Bundle(BaseModel):
    version: str
    commands: dict[str, _Node]
    error: _Node
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


def test_schema_lists_all_commands() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    bundle = _Bundle.model_validate_json(result.stdout)
    assert set(bundle.commands) == {spec.name for spec in COMMANDS}
    assert _flatten(bundle.commands) == {
        path: f"#/$defs/{model.__name__}" for path, model in _result_models(COMMANDS).items()
    }
    assert bundle.error.ref == "#/$defs/ErrorResult"
    assert bundle.version
    for model in [*_result_models(COMMANDS).values(), ErrorResult]:
        assert model.__name__ in bundle.defs


def test_catalog_is_the_single_source_of_truth() -> None:
    cli = build_cli(DEFAULT_DEPENDENCIES)
    registered = {command.name for command in cli.registered_commands}
    groups = {group.name for group in cli.registered_groups}
    hidden = {spec.name for spec in ALIASES}
    assert registered == {
        spec.name for spec in COMMANDS if not isinstance(spec, CommandGroup)
    } | hidden | {"schema"}
    assert groups == {spec.name for spec in COMMANDS if isinstance(spec, CommandGroup)}
    assert hidden.isdisjoint(spec.name for spec in COMMANDS)


def test_schema_map_covers_the_command_result_union() -> None:
    union = set(get_args(CommandResult.__value__))  # pyright: ignore[reportAny]
    assert set(_result_models(COMMANDS).values()) | {ErrorResult} == union


def test_schema_for_command() -> None:
    schema = _CommandSchema.model_validate_json(
        runner.invoke(app, ["schema", "plan", "show"]).stdout
    )
    assert schema.type == "object"
    assert {"command", "project", "plan"} <= set(schema.properties)
    assert {"command", "project", "plan"} <= set(schema.required)
    assert "PlanShowResult" not in schema.defs


@pytest.mark.parametrize("args", [["schema", "task", "nope"], ["schema", "nope"]])
def test_schema_unknown_command(args: list[str]) -> None:
    result = runner.invoke(app, [*args, "--format", "json"])
    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    error = ErrorResult.model_validate_json(result.stderr)
    assert error.command == "schema"
    assert error.code in {"not_found", "input"}


def test_schema_needs_no_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    assert _Bundle.model_validate_json(result.stdout).version


def test_every_leaf_result_command_matches_its_catalog_path() -> None:
    for path, spec in leaves(COMMANDS):
        assert spec.result_model is not None
        annotation = spec.result_model.model_fields["command"].annotation
        command = get_args(getattr(annotation, "__value__", annotation))
        assert path in command, f"{path} result declares {command!r}"
