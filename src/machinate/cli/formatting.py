from collections.abc import Mapping
from functools import singledispatch
from io import StringIO
from typing import override

from rich.console import Console
from rich.table import Table

from .models import (
    AddResult,
    CommandResult,
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ErrorResult,
    InfoResult,
    InitResult,
    ListResult,
    PathResult,
    PlanInfoResult,
    SetResult,
    ShowResult,
    StatusResult,
    TaskAddResult,
    TaskInfoResult,
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


def _counts[S: str](counts: Mapping[S, int]) -> str:
    return ", ".join(f"{name}: {count}" for name, count in counts.items())


@render_text.register
def render_plan_info(result: PlanInfoResult) -> str:
    plan = result.overview.info.plan
    metadata = plan.metadata
    lines = [
        f"Plan {plan.name} ({metadata.status})",
        f"Project: {result.project.name} — {result.project.directory}",
        f"Path: {result.project.storage / plan.path}",
        f"Created: {metadata.created.isoformat()}",
        f"Updated: {plan.last_activity_at.isoformat()}",
    ]
    if metadata.summary:
        lines.append(f"Summary: {metadata.summary}")
    if metadata.tags:
        lines.append(f"Tags: {', '.join(metadata.tags)}")
    tasks = result.overview.info.task_counts
    lines.append(f"Tasks: {sum(tasks.values())} ({_counts(tasks)})")
    lines.append(f"Contexts: {result.overview.info.context_count}")
    return "\n".join(lines)


@render_text.register
def render_info(result: InfoResult) -> str:
    overview = result.overview
    current = overview.current_plan
    if current is not None and not overview.selection_valid:
        current = f"{current} (missing)"
    lines = [
        f"Project {result.project.name} — {result.project.directory}",
        f"Storage: {result.project.storage}",
        f"Current plan: {current or '(none)'}",
        f"Plans: {overview.plan_count} ({_counts(overview.plans_by_status)})",
        f"Tasks: {sum(overview.task_totals.values())} ({_counts(overview.task_totals)})",
        f"Contexts: {overview.context_count}",
    ]
    if overview.recent_plans:
        lines.append("Recent plans:")
        for plan in overview.recent_plans:
            summary = f" — {plan.metadata.summary}" if plan.metadata.summary else ""
            lines.append(f"  {plan.name} ({plan.metadata.status}){summary}")
    return "\n".join(lines)


@render_text.register
def render_add(result: AddResult) -> str:
    return (
        f"Created plan {result.plan.name} in {result.project.name}\n"
        f"Path: {result.project.storage / result.plan.path}"
    )


@render_text.register
def render_context_add(result: ContextAddResult) -> str:
    count = len(result.contexts)
    lines = [f"Created {count} context document(s) in {result.project.name}/{result.plan}"]
    lines.extend(
        f"- {context.name}: {result.project.storage / context.path}" for context in result.contexts
    )
    return "\n".join(lines)


@render_text.register
def render_context_list(result: ContextListResult) -> str:
    output = StringIO()
    console = Console(file=output, color_system=None, width=120, markup=False, highlight=False)
    console.print(f"{result.project.name} / {result.plan}")
    if not result.contexts:
        console.print("No contexts found.")
    else:
        table = Table("Name", "Tags", "Summary", "Updated")
        for entry in result.contexts:
            table.add_row(
                entry.name,
                ", ".join(entry.metadata.tags),
                entry.metadata.summary or "",
                entry.last_activity_at.isoformat(),
            )
        console.print(table)
    return output.getvalue().rstrip()


@render_text.register
def render_context_show(result: ContextShowResult) -> str:
    metadata = result.context.document.metadata
    lines = [
        f"Context {result.context.name}",
        f"Project: {result.project.name} / {result.plan}",
        f"Path: {result.project.storage / result.context.path}",
        f"Created: {metadata.created.isoformat()}",
        f"Modified: {result.context.modified_at.isoformat()}",
    ]
    if metadata.summary:
        lines.append(f"Summary: {metadata.summary}")
    if metadata.tags:
        lines.append(f"Tags: {', '.join(metadata.tags)}")
    body = result.context.document.body.rstrip("\n")
    if body:
        lines.extend(("", body))
    return "\n".join(lines)


@render_text.register
def render_path(result: PathResult) -> str:
    return str(result.path)


@render_text.register
def render_context_info(result: ContextInfoResult) -> str:
    metadata = result.context.metadata
    lines = [
        f"Context {result.context.name}",
        f"Project: {result.project.name} / {result.plan}",
        f"Path: {result.project.storage / result.context.path}",
        f"Created: {metadata.created.isoformat()}",
        f"Modified: {result.context.last_activity_at.isoformat()}",
    ]
    if metadata.summary:
        lines.append(f"Summary: {metadata.summary}")
    if metadata.tags:
        lines.append(f"Tags: {', '.join(metadata.tags)}")
    return "\n".join(lines)


@render_text.register
def render_task_info(result: TaskInfoResult) -> str:
    metadata = result.task.metadata
    lines = [
        f"Task {result.task.name} ({metadata.status})",
        f"Project: {result.project.name} / {result.plan}",
        f"Path: {result.project.storage / result.task.path}",
        f"Created: {metadata.created.isoformat()}",
        f"Modified: {result.task.last_activity_at.isoformat()}",
    ]
    if metadata.summary:
        lines.append(f"Summary: {metadata.summary}")
    if metadata.tags:
        lines.append(f"Tags: {', '.join(metadata.tags)}")
    return "\n".join(lines)


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
        table = Table("Name", "Status", "Tags", "Summary", "Updated")
        for task in result.tasks:
            table.add_row(
                task.name,
                task.metadata.status,
                ", ".join(task.metadata.tags),
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
    if metadata.tags:
        lines.append(f"Tags: {', '.join(metadata.tags)}")
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
    if metadata.tags:
        lines.append(f"Tags: {', '.join(metadata.tags)}")
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
        table = Table("Name", "Status", "Tags", "Summary", "Updated")
        for plan in result.plans:
            table.add_row(
                plan.name,
                plan.metadata.status,
                ", ".join(plan.metadata.tags),
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
