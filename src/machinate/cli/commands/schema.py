import json
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, cast

import typer
from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaValue

from machinate.cli.commands.catalog import COMMANDS, CommandSpec
from machinate.cli.models import ErrorResult


def _leaves(specs: tuple[CommandSpec, ...]) -> Iterator[CommandSpec]:
    for spec in specs:
        if spec.children:
            yield from _leaves(spec.children)
        else:
            yield spec


def _result_models(specs: tuple[CommandSpec, ...]) -> list[type[BaseModel]]:
    return [spec.result for spec in _leaves(specs) if spec.result is not None]


def _schema_results() -> dict[str, type[BaseModel]]:
    results: dict[str, type[BaseModel]] = {}

    def walk(specs: tuple[CommandSpec, ...], prefix: str = "") -> None:
        for spec in specs:
            path = prefix + spec.name
            if spec.children:
                walk(spec.children, prefix=f"{path} ")
            elif spec.result is not None:
                results[path] = spec.result

    walk(COMMANDS)
    return results


SCHEMA_RESULTS: dict[str, type[BaseModel]] = _schema_results()


class UnknownSchemaError(Exception):
    """Raised when a requested schema name is not recognized."""


def _package_version() -> str:
    try:
        return version("machinate")
    except PackageNotFoundError:  # pragma: no cover
        return "0.0.0"


def _ref(result: type[BaseModel]) -> JsonSchemaValue:
    return {"$ref": f"#/$defs/{result.__name__}"}


def _definitions(specs: tuple[CommandSpec, ...]) -> JsonSchemaValue:
    definitions: JsonSchemaValue = {}
    for model in [*_result_models(specs), ErrorResult]:
        schema = model.model_json_schema(mode="serialization")
        definitions.update(cast("JsonSchemaValue", schema.pop("$defs", {})))
        definitions[model.__name__] = schema
    return definitions


def _command_tree(specs: tuple[CommandSpec, ...]) -> JsonSchemaValue:
    tree: JsonSchemaValue = {}
    for spec in specs:
        if spec.children:
            tree[spec.name] = {"commands": _command_tree(spec.children)}
        elif spec.result is not None:
            tree[spec.name] = _ref(spec.result)
    return tree


def schema_bundle() -> JsonSchemaValue:
    """Build a combined schema document mapping each command to its result schema."""
    return {
        "version": _package_version(),
        "commands": _command_tree(COMMANDS),
        "error": _ref(ErrorResult),
        "$defs": _definitions(COMMANDS),
    }


def _find(path: list[str]) -> CommandSpec:
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
    spec = _find(path)
    if spec.children:
        return {"commands": _command_tree(spec.children), "$defs": _definitions(spec.children)}
    if spec.result is not None:
        return spec.result.model_json_schema(mode="serialization")
    msg = f"Command {spec.name!r} has no result schema."
    raise UnknownSchemaError(msg)


def schema_command(
    command: Annotated[
        list[str] | None,
        typer.Argument(help="Command path whose result schema to print; omit for all schemas."),
    ] = None,
) -> None:
    """Print the JSON Schema for command results for agent consumption."""
    try:
        payload = schema_payload(command) if command else schema_bundle()
    except UnknownSchemaError as exc:
        typer.echo(ErrorResult(command="schema", error=str(exc)).model_dump_json(), err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(payload, separators=(",", ":")))
