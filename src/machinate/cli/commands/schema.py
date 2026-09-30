import json
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, ClassVar, cast

import typer
from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaValue

from machinate.cli.commands.catalog import COMMANDS, CommandSpec, leaves
from machinate.cli.execution import execute
from machinate.cli.models import ErrorResult
from machinate.cli.options import OUTPUT_FORMAT
from machinate.models.operations import ErrorCode
from machinate.services.errors import ServiceError


def _result_models(specs: tuple[CommandSpec, ...]) -> dict[str, type[BaseModel]]:
    """Map each leaf command path to its result model, in listing order."""
    return {
        path: spec.result_model for path, spec in leaves(specs) if spec.result_model is not None
    }


class UnknownSchemaError(ServiceError):
    """Raised when a requested schema name is not recognized."""

    code: ClassVar[ErrorCode] = "input"


def _package_version() -> str:
    try:
        return version("machinate")
    except PackageNotFoundError:  # pragma: no cover
        return "0.0.0"


def _ref(result: type[BaseModel]) -> JsonSchemaValue:
    return {"$ref": f"#/$defs/{result.__name__}"}


def _definitions(specs: tuple[CommandSpec, ...]) -> JsonSchemaValue:
    definitions: JsonSchemaValue = {}
    for model in [*_result_models(specs).values(), ErrorResult]:
        schema = model.model_json_schema(mode="serialization")
        definitions.update(cast("JsonSchemaValue", schema.pop("$defs", {})))
        definitions[model.__name__] = schema
    return definitions


def _command_tree(specs: tuple[CommandSpec, ...]) -> JsonSchemaValue:
    tree: JsonSchemaValue = {}
    for spec in specs:
        if spec.children:
            tree[spec.name] = {"commands": _command_tree(spec.children)}
        elif spec.result_model is not None:
            tree[spec.name] = _ref(spec.result_model)
    return tree


def schema_bundle() -> JsonSchemaValue:
    """Build a combined schema document mapping each command to its result schema."""
    return {
        "version": _package_version(),
        "commands": _command_tree(COMMANDS),
        "error": _ref(ErrorResult),
        "$defs": _definitions(COMMANDS),
    }


def _get_spec(path: list[str]) -> CommandSpec:
    specs = COMMANDS
    spec: CommandSpec | None = None
    for part in path:
        spec = next((candidate for candidate in specs if candidate.name == part), None)
        if spec is None:
            available = ", ".join(candidate.name for candidate in specs)
            msg = f"Unknown schema {part!r}. Available schemas: {available}"
            raise UnknownSchemaError(msg)
        specs = spec.children
    if spec is None:
        msg = "No schema requested."
        raise UnknownSchemaError(msg)
    return spec


def schema_payload(path: list[str]) -> JsonSchemaValue:
    """Return the JSON Schema for a command path (or the error envelope)."""
    if path == ["error"]:
        return ErrorResult.model_json_schema(mode="serialization")
    spec = _get_spec(path)
    if spec.children:
        return {"commands": _command_tree(spec.children), "$defs": _definitions(spec.children)}
    if spec.result_model is not None:
        return spec.result_model.model_json_schema(mode="serialization")
    msg = f"Command {spec.name!r} has no result schema."
    raise UnknownSchemaError(msg)


def schema_command(
    ctx: typer.Context,
    command: Annotated[
        list[str] | None,
        typer.Argument(help="Command path whose result schema to print; omit for all schemas."),
    ] = None,
    output_format: OUTPUT_FORMAT = None,
) -> None:
    """Print the JSON Schema for command results for agent consumption."""
    with execute(ctx, output_format):
        payload = schema_payload(command) if command else schema_bundle()
        typer.echo(json.dumps(payload, separators=(",", ":")))
