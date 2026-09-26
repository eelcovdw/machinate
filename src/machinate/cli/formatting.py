from collections.abc import Mapping
from io import StringIO
from typing import override

from rich.console import Console
from rich.table import Table

from .models import CommandResult, ErrorResult


class Formatter:
    def format(self, result: CommandResult) -> str:
        return result.model_dump_json()


class TextFormatter(Formatter):
    @override
    def format(self, result: CommandResult) -> str:
        if isinstance(result, ErrorResult):
            return f"Error: {result.error}"
        output = StringIO()
        console = Console(file=output, color_system=None, width=120, markup=False, highlight=False)
        console.print(f"{result.project.name} — {result.project.directory}")
        console.print(f"Storage: {result.project.storage}")
        if not result.plans:
            console.print("No plans found.")
        else:
            table = Table("Name", "Status", "Summary", "Updated")
            for plan in result.plans:
                table.add_row(
                    plan.name,
                    plan.metadata.status,
                    plan.metadata.summary or "",
                    plan.last_activity_at.isoformat(),
                )
            console.print(table)
        return output.getvalue().rstrip()


class UnknownFormatError(Exception):
    pass


def select_formatter(name: str, formatters: Mapping[str, Formatter]) -> Formatter:
    try:
        return formatters[name]
    except KeyError as exc:
        message = f"Unknown format {name!r}. Available formats: {', '.join(formatters)}"
        raise UnknownFormatError(message) from exc
