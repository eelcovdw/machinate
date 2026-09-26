import logging
from contextlib import suppress
from typing import TextIO, override

import click
import typer
from pydantic import ValidationError
from typer.core import TyperCommand

from .commands.catalog import ALIASES, COMMANDS, CommandSpec
from .commands.schema import schema_command
from .dependencies import Dependencies, get_dependencies
from .errors import describe_error
from .formatting import Formatter, UnknownFormatError, select_formatter
from .models import ErrorResult
from .settings import Settings


class Command(TyperCommand):
    """Render command parsing failures through the configured formatter."""

    @override
    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        original_args = args.copy()
        try:
            return super().parse_args(ctx, args)
        except click.UsageError as exc:
            # Recover parsed options without invoking callbacks or normal help.
            recovered = self.make_context(
                ctx.info_name,
                original_args,
                parent=ctx.parent,
                resilient_parsing=True,
                ignore_unknown_options=True,
            )
            with recovered:
                override_name = recovered.params.get("output_format")
                formatter = Formatter()
                message = exc.format_message()
                try:
                    settings = Settings()
                    name = override_name if isinstance(override_name, str) else settings.format
                    formatter = select_formatter(name, get_dependencies(ctx).formatters)
                except (ValidationError, UnknownFormatError) as formatting_error:
                    message = describe_error(formatting_error)
                typer.echo(
                    formatter.format(ErrorResult(command=_command_label(ctx), error=message)),
                    err=True,
                )
            raise typer.Exit(2) from exc


def _command_label(ctx: click.Context) -> str:
    """Build the space-separated command path for structured errors."""
    names: list[str] = []
    current = ctx
    while current.parent is not None:
        if current.info_name:
            names.append(current.info_name)
        current = current.parent
    return " ".join(reversed(names)) or "plan"


class _DiagnosticHandler(logging.StreamHandler[TextIO]):
    """stderr handler for opt-in diagnostics; the subclass prevents duplicates."""


def configure_logging(settings: Settings) -> None:
    """Route Machinate logs to stderr when MACHI_LOG_LEVEL is set."""
    if settings.log_level is None:
        return
    logger = logging.getLogger("machinate")
    for handler in list(logger.handlers):
        if isinstance(handler, _DiagnosticHandler):
            logger.removeHandler(handler)
    handler = _DiagnosticHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(settings.log_level)


def root() -> None:
    """Work with Machinate projects."""
    # Invalid settings are reported by the command handler through its formatter.
    with suppress(ValidationError):
        configure_logging(Settings())


def _register(parent: typer.Typer, spec: CommandSpec) -> None:
    if spec.children:
        group = typer.Typer(no_args_is_help=True)
        for child in spec.children:
            _register(group, child)
        parent.add_typer(group, name=spec.name)
    elif spec.handler is not None:
        parent.command(spec.name, cls=Command)(spec.handler)


def create_cli(dependencies: Dependencies | None = None) -> typer.Typer:
    cli = typer.Typer(
        no_args_is_help=True,
        context_settings={"obj": dependencies if dependencies is not None else Dependencies()},
    )
    cli.callback()(root)
    for spec in COMMANDS:
        _register(cli, spec)
    for alias in ALIASES:
        if alias.handler is not None:
            cli.command(alias.name, cls=Command, hidden=True)(alias.handler)
    cli.command("schema", cls=Command)(schema_command)
    return cli


app = create_cli()
