from contextlib import suppress
from typing import cast, override

import click
import typer
from pydantic import ValidationError
from typer.core import TyperCommand, TyperGroup

from .commands.catalog import ALIASES, COMMANDS, CommandSpec
from .commands.schema import schema_command
from .dependencies import Dependencies, get_dependencies, get_settings
from .errors import EXIT_USAGE, describe_error
from .execution import command_label, resolve_formatter
from .formatting import JsonFormatter, UnknownFormatError
from .models import ErrorResult
from .settings import Settings


class Command(TyperCommand):
    """Render leaf-command parsing failures through the configured formatter."""

    @override
    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        original_args = args.copy()
        try:
            return super().parse_args(ctx, args)
        except click.UsageError as exc:
            _report_usage_error(ctx, exc, original_args)
            raise typer.Exit(EXIT_USAGE) from exc


class Group(TyperGroup):
    """Render group parsing failures through the configured formatter."""

    @override
    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        original_args = args.copy()
        try:
            return super().parse_args(ctx, args)
        except click.exceptions.NoArgsIsHelpError:
            raise
        except click.UsageError as exc:
            _report_usage_error(ctx, exc, original_args)
            raise typer.Exit(EXIT_USAGE) from exc

    @override
    def invoke(self, ctx: click.Context) -> object:
        try:
            return cast("object", super().invoke(ctx))
        except click.exceptions.NoArgsIsHelpError:
            raise
        except click.UsageError as exc:
            # Unknown subcommands and other resolution failures reach here.
            _report_usage_error(ctx, exc, None)
            raise typer.Exit(EXIT_USAGE) from exc


def _report_usage_error(
    ctx: click.Context,
    exc: click.UsageError,
    original_args: list[str] | None,
) -> None:
    """Format a usage failure using the flag, settings, or default formatter."""
    message = exc.format_message()
    formatter = JsonFormatter()  # Structured fallback if settings/format selection fails.
    override_name: object = None
    if original_args is not None:
        # Recover parsed options without invoking callbacks or normal help.
        recovered = ctx.command.make_context(
            ctx.info_name,
            original_args,
            parent=ctx.parent,
            resilient_parsing=True,
            ignore_unknown_options=True,
        )
        with recovered:
            override_name = recovered.params.get("output_format")
    try:
        override = override_name if isinstance(override_name, str) else None
        formatter = resolve_formatter(override, get_settings(ctx), get_dependencies(ctx))
    except (ValidationError, UnknownFormatError) as formatting_error:
        message = describe_error(formatting_error).message
    typer.echo(
        formatter.format(ErrorResult(command=command_label(ctx), error=message, code="input")),
        err=True,
    )


def configure_logging(settings: Settings) -> None:
    """Route Machinate logs to stderr when MACHI_LOG_LEVEL is set."""
    if settings.log_level is None:
        return
    # Imported lazily: logging is only needed when diagnostics are actually enabled.
    import logging
    from typing import TextIO

    class _DiagnosticHandler(logging.StreamHandler[TextIO]):
        """stderr handler for opt-in diagnostics; the subclass prevents duplicates."""

    logger = logging.getLogger("machinate")
    for handler in list(logger.handlers):
        if isinstance(handler, _DiagnosticHandler):
            logger.removeHandler(handler)
    handler = _DiagnosticHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(settings.log_level)


def root(ctx: typer.Context) -> None:
    """Work with Machinate projects."""
    # Invalid settings are reported by the command handler through its formatter.
    with suppress(ValidationError):
        configure_logging(get_settings(ctx))


def _register(parent: typer.Typer, spec: CommandSpec) -> None:
    if spec.children:
        group = typer.Typer(no_args_is_help=True, cls=Group, rich_markup_mode=None)
        for child in spec.children:
            _register(group, child)
        parent.add_typer(group, name=spec.name, help=spec.help)
    elif spec.handler is not None:
        parent.command(spec.name, cls=Command)(spec.handler)


def build_cli(dependencies: Dependencies | None = None) -> typer.Typer:
    cli = typer.Typer(
        no_args_is_help=True,
        cls=Group,
        rich_markup_mode=None,
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


app = build_cli()
