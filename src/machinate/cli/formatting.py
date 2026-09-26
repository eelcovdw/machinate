import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from functools import singledispatch
from io import StringIO
from typing import get_args, override

from rich.console import Console
from rich.text import Text

from machinate.storage import PlanStatus, TaskStatus

from .models import (
    AddResult,
    CommandResult,
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ContextUpdateResult,
    ErrorResult,
    InfoResult,
    InitResult,
    ListResult,
    PathResult,
    PlanInfoResult,
    SetResult,
    ShowResult,
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
    UpdateResult,
)
from .styles import (
    ERROR,
    HEADING,
    LABEL,
    MUTED,
    PATH,
    PROJECT,
    TIMESTAMP,
    status_style,
)

PLAN_STATUS_ORDER: Sequence[str] = get_args(PlanStatus.__value__)  # pyright: ignore[reportAny]
TASK_STATUS_ORDER: Sequence[str] = get_args(TaskStatus.__value__)  # pyright: ignore[reportAny]
_CONSOLE_WIDTH = 120
_MIN_SUMMARY_WIDTH = 20


class Formatter:
    def format(self, result: CommandResult) -> str:
        return result.model_dump_json()


@singledispatch
def render_text(result: CommandResult) -> str:
    """Render a command result as text, falling back to JSON when unrecognized."""
    return Formatter().format(result)


def _use_color() -> bool:
    """Style output only on a terminal, honoring the NO_COLOR convention."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _display_width() -> int:
    """Layout width: the terminal's when attached, else a fixed default for pipes and tests."""
    if sys.stdout.isatty():
        return shutil.get_terminal_size().columns
    return _CONSOLE_WIDTH


def _console(output: StringIO) -> Console:
    color = _use_color()
    return Console(
        file=output,
        width=_display_width(),
        markup=False,
        highlight=False,
        force_terminal=color,
        color_system="standard" if color else None,
    )


def _render(lines: Sequence[Text]) -> str:
    """Join styled lines into one string; styling is only emitted when color is on."""
    output = StringIO()
    console = _console(output)
    for line in lines:
        console.print(line, soft_wrap=True)
    return output.getvalue().rstrip()


def _title(kind: str, name: str, status: str | None = None) -> Text:
    line = Text()
    line.append(f"{kind} {name}", style=HEADING)
    if status is not None:
        line.append(" (", style=HEADING)
        line.append(status, style=status_style(status))
        line.append(")", style=HEADING)
    return line


def _field(label: str, value: str | Text, *, style: str = "") -> Text:
    line = Text()
    line.append(f"{label}: ", style=LABEL)
    if isinstance(value, Text):
        line.append_text(value)
    else:
        line.append(value, style=style)
    return line


def _bullet(name: str, value: str) -> Text:
    return Text.assemble(("- ", ""), (name, HEADING), (f": {value}", PATH))


def _counts[S: str](counts: Mapping[S, int]) -> str:
    return ", ".join(f"{name}: {count}" for name, count in counts.items())


def _shorten(text: str, width: int) -> str:
    """Trim ``text`` to roughly ``width``, preferring a sentence boundary."""
    if width <= 0 or len(text) <= width:
        return text
    head = text[: width + 1]
    for stop in (". ", "! ", "? "):
        index = head.rfind(stop)
        if index >= width // 2:
            return text[: index + 1]
    space = head.rfind(" ")
    cut = space if space > 0 else width
    return f"{text[:cut].rstrip()}…"


def _entry(name: str, name_width: int, tags: str, tags_width: int, summary: str | None) -> Text:
    line = Text("  ")
    if summary:
        line.append(name.ljust(name_width))
        line.append("  ")
        line.append(tags.ljust(tags_width), style=MUTED)
        line.append("  ")
        available = _display_width() - (2 + name_width + 2 + tags_width + 2)
        line.append(_shorten(summary, max(available, _MIN_SUMMARY_WIDTH)))
    elif tags:
        line.append(name.ljust(name_width))
        line.append("  ")
        line.append(tags, style=MUTED)
    else:
        line.append(name)
    return line


def _status_sections(entries: Sequence[tuple[str, Text]], statuses: Sequence[str]) -> list[Text]:
    """Group entry rows under colored status headers, known statuses first."""
    grouped: dict[str, list[Text]] = {}
    for status, row in entries:
        grouped.setdefault(status, []).append(row)
    order = list(statuses)
    order.extend(status for status in grouped if status not in statuses)
    lines: list[Text] = []
    for status in order:
        rows = grouped.get(status, [])
        header = Text(status, style=status_style(status))
        header.append(f" ({len(rows)})", style=MUTED)
        lines.append(header)
        lines.extend(rows)
    return lines


@render_text.register
def render_error(result: ErrorResult) -> str:
    return _render([Text(f"Error: {result.error}", style=ERROR)])


@render_text.register
def render_plan_info(result: PlanInfoResult) -> str:
    info = result.overview.info
    plan = info.plan
    metadata = plan.metadata
    lines = [
        _title("Plan", plan.name, metadata.status),
        _field("Project", f"{result.project.name} — {result.project.directory}"),
        _field("Path", str(result.project.storage / plan.path), style=PATH),
        _field("Created", metadata.created.isoformat(), style=TIMESTAMP),
        _field("Updated", plan.last_activity_at.isoformat(), style=TIMESTAMP),
    ]
    if plan.summary:
        lines.append(_field("Summary", plan.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    tasks = info.task_counts
    lines.append(_field("Tasks", f"{sum(tasks.values())} ({_counts(tasks)})"))
    lines.append(_field("Contexts", str(info.context_count)))
    return _render(lines)


@render_text.register
def render_info(result: InfoResult) -> str:
    overview = result.overview
    current = overview.current_plan
    if current is not None and not overview.selection_valid:
        current = f"{current} (missing)"
    lines = [
        Text(f"Project {result.project.name} — {result.project.directory}", style=PROJECT),
        _field("Storage", str(result.project.storage), style=PATH),
        _field("Current plan", current or "(none)", style="" if current else MUTED),
        _field("Plans", f"{overview.plan_count} ({_counts(overview.plans_by_status)})"),
        _field("Tasks", f"{sum(overview.task_totals.values())} ({_counts(overview.task_totals)})"),
        _field("Contexts", str(overview.context_count)),
    ]
    if overview.recent_plans:
        lines.append(Text("Recent plans:", style=HEADING))
        for plan in overview.recent_plans:
            line = Text("  ")
            line.append(plan.name, style=HEADING)
            line.append(" (")
            line.append(plan.metadata.status, style=status_style(plan.metadata.status))
            line.append(")")
            if plan.summary:
                line.append(f" — {plan.summary}")
            lines.append(line)
    return _render(lines)


@render_text.register
def render_add(result: AddResult) -> str:
    lines = [
        Text(f"Created plan {result.plan.name} in {result.project.name}", style=HEADING),
        _field("Path", str(result.project.storage / result.plan.path), style=PATH),
    ]
    return _render(lines)


@render_text.register
def render_context_add(result: ContextAddResult) -> str:
    location = f"{result.project.name}/{result.plan}"
    lines = [
        Text(f"Created {len(result.contexts)} context document(s) in {location}", style=HEADING)
    ]
    lines.extend(
        _bullet(context.name, str(result.project.storage / context.path))
        for context in result.contexts
    )
    return _render(lines)


@render_text.register
def render_context_list(result: ContextListResult) -> str:
    lines = [Text(f"{result.project.name} / {result.plan}", style=PROJECT)]
    if not result.contexts:
        lines.append(Text("No contexts found.", style=MUTED))
        return _render(lines)
    lines.append(Text())
    name_width = max(len(entry.name) for entry in result.contexts)
    tags = [", ".join(entry.metadata.tags) for entry in result.contexts]
    tags_width = max((len(value) for value in tags), default=0)
    lines.extend(
        _entry(entry.name, name_width, tag, tags_width, entry.summary)
        for entry, tag in zip(result.contexts, tags, strict=True)
    )
    return _render(lines)


@render_text.register
def render_context_show(result: ContextShowResult) -> str:
    metadata = result.context.document.metadata
    lines = [
        _title("Context", result.context.name),
        _field("Project", f"{result.project.name} / {result.plan}"),
        _field("Path", str(result.project.storage / result.context.path), style=PATH),
        _field("Created", metadata.created.isoformat(), style=TIMESTAMP),
        _field("Modified", result.context.modified_at.isoformat(), style=TIMESTAMP),
    ]
    context_summary = result.context.document.get_or_derive_summary()
    if context_summary:
        lines.append(_field("Summary", context_summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    body = result.context.document.body.rstrip("\n")
    if body:
        lines.extend((Text(""), Text(body)))
    return _render(lines)


@render_text.register
def render_path(result: PathResult) -> str:
    return str(result.path)


@render_text.register
def render_context_info(result: ContextInfoResult) -> str:
    metadata = result.context.metadata
    lines = [
        _title("Context", result.context.name),
        _field("Project", f"{result.project.name} / {result.plan}"),
        _field("Path", str(result.project.storage / result.context.path), style=PATH),
        _field("Created", metadata.created.isoformat(), style=TIMESTAMP),
        _field("Modified", result.context.last_activity_at.isoformat(), style=TIMESTAMP),
    ]
    if result.context.summary:
        lines.append(_field("Summary", result.context.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    return _render(lines)


@render_text.register
def render_task_info(result: TaskInfoResult) -> str:
    metadata = result.task.metadata
    lines = [
        _title("Task", result.task.name, metadata.status),
        _field("Project", f"{result.project.name} / {result.plan}"),
        _field("Path", str(result.project.storage / result.task.path), style=PATH),
        _field("Created", metadata.created.isoformat(), style=TIMESTAMP),
        _field("Modified", result.task.last_activity_at.isoformat(), style=TIMESTAMP),
    ]
    if result.task.summary:
        lines.append(_field("Summary", result.task.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    return _render(lines)


@render_text.register
def render_task_add(result: TaskAddResult) -> str:
    lines = [
        Text(
            f"Created {len(result.tasks)} task(s) in {result.project.name}/{result.plan}",
            style=HEADING,
        )
    ]
    lines.extend(
        _bullet(task.name, str(result.project.storage / task.path)) for task in result.tasks
    )
    return _render(lines)


@render_text.register
def render_task_list(result: TaskListResult) -> str:
    lines = [Text(f"{result.project.name} / {result.plan}", style=PROJECT)]
    if not result.tasks:
        lines.append(Text("No tasks found.", style=MUTED))
        return _render(lines)
    lines.append(Text())
    name_width = max(len(task.name) for task in result.tasks)
    tags = [", ".join(task.metadata.tags) for task in result.tasks]
    tags_width = max((len(value) for value in tags), default=0)
    entries = [
        (
            task.metadata.status,
            _entry(task.name, name_width, tag, tags_width, task.summary),
        )
        for task, tag in zip(result.tasks, tags, strict=True)
    ]
    lines.extend(_status_sections(entries, TASK_STATUS_ORDER))
    return _render(lines)


@render_text.register
def render_task_update(result: TaskUpdateResult) -> str:
    status = result.task.document.metadata.status
    line = Text("Updated task ")
    line.append(result.task.name, style=HEADING)
    line.append(f" in {result.project.name}/{result.plan} (")
    line.append(status, style=status_style(status))
    line.append(")")
    return _render([line])


@render_text.register
def render_context_update(result: ContextUpdateResult) -> str:
    line = Text("Updated context ")
    line.append(result.context.name, style=HEADING)
    line.append(f" in {result.project.name}/{result.plan}")
    return _render([line])


@render_text.register
def render_task_show(result: TaskShowResult) -> str:
    metadata = result.task.document.metadata
    lines = [
        _title("Task", result.task.name, metadata.status),
        _field("Project", f"{result.project.name} / {result.plan}"),
        _field("Path", str(result.project.storage / result.task.path), style=PATH),
        _field("Created", metadata.created.isoformat(), style=TIMESTAMP),
        _field("Modified", result.task.modified_at.isoformat(), style=TIMESTAMP),
    ]
    task_summary = result.task.document.get_or_derive_summary()
    if task_summary:
        lines.append(_field("Summary", task_summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    body = result.task.document.body.rstrip("\n")
    if body:
        lines.extend((Text(""), Text(body)))
    return _render(lines)


@render_text.register
def render_show(result: ShowResult) -> str:
    metadata = result.plan.document.metadata
    lines = [
        _title("Plan", result.plan.name, metadata.status),
        _field("Project", f"{result.project.name} — {result.project.directory}"),
        _field("Path", str(result.project.storage / result.plan.path), style=PATH),
        _field("Created", metadata.created.isoformat(), style=TIMESTAMP),
        _field("Modified", result.plan.modified_at.isoformat(), style=TIMESTAMP),
    ]
    plan_summary = result.plan.document.get_or_derive_summary()
    if plan_summary:
        lines.append(_field("Summary", plan_summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    body = result.plan.document.body.rstrip("\n")
    if body:
        lines.extend((Text(""), Text(body)))
    return _render(lines)


@render_text.register
def render_update(result: UpdateResult) -> str:
    status = result.plan.document.metadata.status
    line = Text("Updated plan ")
    line.append(result.plan.name, style=HEADING)
    line.append(f" in {result.project.name} (")
    line.append(status, style=status_style(status))
    line.append(")")
    return _render([line])


@render_text.register
def render_set(result: SetResult) -> str:
    line = Text("Selected plan ")
    line.append(str(result.state.current_plan), style=HEADING)
    line.append(f" in {result.project.name}")
    return _render([line])


@render_text.register
def render_init(result: InitResult) -> str:
    lines = [
        Text(f"Initialized {result.project.name} at {result.project.directory}", style=HEADING),
        _field("Storage", str(result.project.storage), style=PATH),
    ]
    return _render(lines)


@render_text.register
def render_list(result: ListResult) -> str:
    lines = [
        Text(f"{result.project.name} — {result.project.directory}", style=PROJECT),
        _field("Storage", str(result.project.storage), style=PATH),
    ]
    if not result.plans:
        lines.append(Text("No plans found.", style=MUTED))
        return _render(lines)
    lines.append(Text())
    name_width = max(len(plan.name) for plan in result.plans)
    tags = [", ".join(plan.metadata.tags) for plan in result.plans]
    tags_width = max((len(value) for value in tags), default=0)
    entries = [
        (
            plan.metadata.status,
            _entry(plan.name, name_width, tag, tags_width, plan.summary),
        )
        for plan, tag in zip(result.plans, tags, strict=True)
    ]
    lines.extend(_status_sections(entries, PLAN_STATUS_ORDER))
    return _render(lines)


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
