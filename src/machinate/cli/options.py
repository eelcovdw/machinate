"""Shared CLI option definitions."""

from typing import Annotated

import click
import typer

from .dependencies import get_dependencies


def validate_output_format(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Reject unknown formatter names as a usage error, keeping custom formatters usable."""
    if value is None:
        return None
    names = get_dependencies(ctx).formatters
    if value not in names:
        choices = ", ".join(sorted(names))
        message = f"{value!r} is not a known formatter; choose from {choices}."
        raise click.BadParameter(message, ctx=ctx, param=param, param_hint="'--format'")
    return value


OUTPUT_FORMAT = Annotated[
    str | None,
    typer.Option(
        "--format",
        callback=validate_output_format,
        help="Formatter name (text or json by default).",
    ),
]
