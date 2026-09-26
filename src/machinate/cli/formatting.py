from collections.abc import Mapping
from functools import singledispatch
from io import StringIO
from typing import override

from rich.console import Console
from rich.table import Table

from .models import (
    AddResult,
    CommandResult,
    ErrorResult,
    InitResult,
    ListResult,
    SetResult,
    ShowResult,
    StatusResult,
    TaskAddResult,
    TaskListResult,
    TaskShowResult,
    TaskStatusResult,
)


class Formatter:
    def format(self, result: CommandResult) -> str:
        return result.model_dump_json()


@singledispatch
def render_text(result: CommandResult) -> str:
    """Render a command result as text, falling back to JSON when unrecognized."""
    return Formatter().format(result)


@render_text.register
def render_error(result: ErrorResult) -> str:
    return f"Error: {result.error}"


@render_text.register
def render_add(result: AddResult) -> str:
    return (
        f"Created plan {result.plan.name} in {result.project.name}\n"
        f"Path: {result.project.storage / result.plan.path}"
    )


@render_text.register
def render_task_add(result: TaskAddResult) -> str:
    lines = [f"Created {len(result.tasks)} task(s) in {result.project.name}/{result.plan}"]
    lines.extend(f"- {task.name}: {result.project.storage / task.path}" for task in result.tasks)
    return "\n".join(lines)


@render_text.register
def render_task_list(result: TaskListResult) -> str:
    output = StringIO()
    console = Console(file=output, color_system=None, width=120, markup=False, highlight=False)
    console.print(f"{result.project.name} / {result.plan}")
    if not result.tasks:
        console.print("No tasks found.")
    else:
        table = Table("Name", "Status", "Summary", "Updated")
        for task in result.tasks:
            table.add_row(
                task.name,
                task.metadata.status,
                task.metadata.summary or "",
                task.last_activity_at.isoformat(),
            )
        console.print(table)
    return output.getvalue().rstrip()


@render_text.register
def render_task_status(result: TaskStatusResult) -> str:
    status = result.task.document.metadata.status
    return f"Task {result.task.name} is {status} in {result.project.name}/{result.plan}"


@render_text.register
def render_task_show(result: TaskShowResult) -> str:
    metadata = result.task.document.metadata
    lines = [
        f"Task {result.task.name} ({metadata.status})",
        f"Project: {result.project.name} / {result.plan}",
        f"Path: {result.project.storage / result.task.path}",
        f"Created: {metadata.created.isoformat()}",
        f"Modified: {result.task.modified_at.isoformat()}",
    ]
    if metadata.summary:
        lines.append(f"Summary: {metadata.summary}")
    body = result.task.document.body.rstrip("\n")
    if body:
        lines.extend(("", body))
    return "\n".join(lines)


@render_text.register
def render_show(result: ShowResult) -> str:
    metadata = result.plan.document.metadata
    lines = [
        f"Plan {result.plan.name} ({metadata.status})",
        f"Project: {result.project.name} — {result.project.directory}",
        f"Path: {result.project.storage / result.plan.path}",
        f"Created: {metadata.created.isoformat()}",
        f"Modified: {result.plan.modified_at.isoformat()}",
    ]
    if metadata.summary:
        lines.append(f"Summary: {metadata.summary}")
    body = result.plan.document.body.rstrip("\n")
    if body:
        lines.extend(("", body))
    return "\n".join(lines)


@render_text.register
def render_status(result: StatusResult) -> str:
    name = result.plan.name
    status = result.plan.document.metadata.status
    return f"Plan {name} is {status} in {result.project.name}"


@render_text.register
def render_set(result: SetResult) -> str:
    return f"Selected plan {result.state.current_plan} in {result.project.name}"


@render_text.register
def render_init(result: InitResult) -> str:
    return (
        f"Initialized {result.project.name} at {result.project.directory}\n"
        f"Storage: {result.project.storage}"
    )


@render_text.register
def render_list(result: ListResult) -> str:
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


class TextFormatter(Formatter):
    @override
    def format(self, result: CommandResult) -> str:
        return render_text(result)


class UnknownFormatError(Exception):
    pass


def select_formatter(name: str, formatters: Mapping[str, Formatter]) -> Formatter:
    try:
        return formatters[name]
    except KeyError as exc:
        message = f"Unknown format {name!r}. Available formats: {', '.join(formatters)}"
        raise UnknownFormatError(message) from exc
