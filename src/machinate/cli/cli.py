from typing import override

import click
import typer
from pydantic import ValidationError
from typer.core import TyperCommand

from .commands.plans import list_plans
from .dependencies import Dependencies, get_dependencies
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
                    name = settings.formatter_name(
                        override_name if isinstance(override_name, str) else None
                    )
                    formatter = select_formatter(name, get_dependencies(ctx).formatters)
                except (ValidationError, UnknownFormatError) as formatting_error:
                    message = str(formatting_error)
                typer.echo(formatter.format(ErrorResult(error=message)), err=True)
            raise typer.Exit(2) from exc


def root() -> None:
    """Work with Machinate projects."""


def create_cli(dependencies: Dependencies | None = None) -> typer.Typer:
    cli = typer.Typer(
        no_args_is_help=True,
        context_settings={"obj": dependencies if dependencies is not None else Dependencies()},
    )
    cli.callback()(root)
    cli.command("list", cls=Command)(list_plans)
    return cli


app = create_cli()
