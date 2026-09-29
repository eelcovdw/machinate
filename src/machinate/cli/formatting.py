import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from functools import singledispatch
from io import StringIO
from typing import get_args, override

from rich.console import Console, RenderableType
from rich.table import Table
from rich.text import Text

from machinate.models.documents import PlanStatus, TaskStatus
from machinate.models.operations import BatchCreateError, FindEntry

from .models import (
    CommandResult,
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ContextUpdateResult,
    DocAddResult,
    DocInfoResult,
    DocListResult,
    DocShowResult,
    DocUpdateResult,
    ErrorResult,
    FindResult,
    InfoResult,
    InitResult,
    InstructionsResult,
    PathResult,
    PlanAddResult,
    PlanInfoResult,
    PlanListResult,
    PlanSelectResult,
    PlanShowResult,
    PlanUnselectResult,
    PlanUpdateResult,
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
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


def _render(lines: Sequence[RenderableType]) -> str:
    """Join styled lines into one string; styling is only emitted when color is on."""
    output = StringIO()
    console = _console(output)
    for line in lines:
        console.print(line, soft_wrap=True)
    rendered = output.getvalue().splitlines()
    return "\n".join(line.rstrip() for line in rendered).rstrip()


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


def _bullet(name: str, value: str, *, style: str = PATH) -> Text:
    return Text.assemble(("- ", ""), (name, HEADING), (f": {value}", style))


def _not_created(errors: Sequence[BatchCreateError]) -> list[Text]:
    """Render the names a batch rejected, so text output never drops them."""
    if not errors:
        return []
    lines = [Text(), Text("Not created:", style=ERROR)]
    lines.extend(_bullet(error.name, error.error, style=ERROR) for error in errors)
    return lines


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


def _entry(  # noqa: PLR0913
    name: str,
    name_width: int,
    tags: str,
    tags_width: int,
    summary: str | None,
    status: str | None = None,
    status_width: int = 0,
) -> Text:
    line = Text("  ")
    used = 2
    if status is not None:
        line.append(status.ljust(status_width), style=status_style(status))
        line.append("  ")
        used += status_width + 2
    if summary:
        line.append(name.ljust(name_width))
        line.append("  ")
        line.append(tags.ljust(tags_width), style=MUTED)
        line.append("  ")
        available = _display_width() - (used + name_width + 2 + tags_width + 2)
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
    order = [status for status in statuses if status in grouped]
    order.extend(status for status in grouped if status not in statuses)
    lines: list[Text] = []
    for status in order:
        rows = grouped[status]
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
    info = result.overview
    plan = info.plan
    metadata = plan.metadata
    lines = [
        _title("Plan", plan.name, metadata.status),
        _field("Project", f"{result.project.name} — {result.project.directory}"),
        _field("Path", str(result.project.storage / plan.path), style=PATH),
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field(
            "Last activity",
            plan.last_activity_at.isoformat(),
            style=TIMESTAMP,
        ),
    ]
    if plan.summary:
        lines.append(_field("Summary", plan.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    tasks = info.tasks_by_status
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
        _field(
            "Tasks",
            f"{sum(overview.tasks_by_status.values())} ({_counts(overview.tasks_by_status)})",
        ),
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
def render_add(result: PlanAddResult) -> str:
    lines = [
        Text(f"Created plan {result.plan.name} in {result.project.name}", style=HEADING),
        _field("Path", str(result.project.storage / result.plan.path), style=PATH),
    ]
    return _render(lines)


@render_text.register
def render_context_add(result: ContextAddResult) -> str:
    location = f"{result.project.name}/{result.plan}"
    lines = [
        Text(
            f"Created {len(result.batch.created)} context document(s) in {location}",
            style=HEADING,
        )
    ]
    lines.extend(
        _bullet(context.name, str(result.project.storage / context.path))
        for context in result.batch.created
    )
    lines.extend(_not_created(result.batch.errors))
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
    metadata = result.context.metadata
    lines = [
        _title("Context", result.context.name),
        _field("Project", f"{result.project.name} / {result.plan}"),
        _field("Path", str(result.project.storage / result.context.path), style=PATH),
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field("Modified", result.context.modified_at.isoformat(), style=TIMESTAMP),
    ]
    if result.context.summary:
        lines.append(_field("Summary", result.context.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    body = result.body.rstrip("\n")
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
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field("Modified", result.context.modified_at.isoformat(), style=TIMESTAMP),
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
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field("Modified", result.task.modified_at.isoformat(), style=TIMESTAMP),
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
            f"Created {len(result.batch.created)} task(s) in {result.project.name}/{result.plan}",
            style=HEADING,
        )
    ]
    lines.extend(
        _bullet(task.name, str(result.project.storage / task.path)) for task in result.batch.created
    )
    lines.extend(_not_created(result.batch.errors))
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
    grouped = result.group_by is not None
    status_width = max((len(task.metadata.status) for task in result.tasks), default=0)
    entries = [
        (
            task.metadata.status,
            _entry(
                task.name,
                name_width,
                tag,
                tags_width,
                task.summary,
                status=None if grouped else task.metadata.status,
                status_width=status_width,
            ),
        )
        for task, tag in zip(result.tasks, tags, strict=True)
    ]
    if grouped:
        lines.extend(_status_sections(entries, TASK_STATUS_ORDER))
    else:
        lines.extend(row for _, row in entries)
    return _render(lines)


@render_text.register
def render_task_update(result: TaskUpdateResult) -> str:
    status = result.task.metadata.status
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
def render_doc_add(result: DocAddResult) -> str:
    lines = [
        Text(
            f"Created {len(result.batch.created)} document(s) in {result.project.name}",
            style=HEADING,
        )
    ]
    lines.extend(
        _bullet(doc.name, str(result.project.storage / doc.path)) for doc in result.batch.created
    )
    lines.extend(_not_created(result.batch.errors))
    return _render(lines)


@render_text.register
def render_doc_list(result: DocListResult) -> str:
    lines = [Text(result.project.name, style=PROJECT)]
    if not result.docs:
        lines.append(Text("No documents found.", style=MUTED))
        return _render(lines)
    lines.append(Text())
    name_width = max(len(entry.name) for entry in result.docs)
    tags = [", ".join(entry.metadata.tags) for entry in result.docs]
    tags_width = max((len(value) for value in tags), default=0)
    lines.extend(
        _entry(entry.name, name_width, tag, tags_width, entry.summary)
        for entry, tag in zip(result.docs, tags, strict=True)
    )
    return _render(lines)


@render_text.register
def render_doc_show(result: DocShowResult) -> str:
    metadata = result.doc.metadata
    lines = [
        _title("Doc", result.doc.name),
        _field("Project", result.project.name),
        _field("Path", str(result.project.storage / result.doc.path), style=PATH),
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field("Modified", result.doc.modified_at.isoformat(), style=TIMESTAMP),
    ]
    if result.doc.summary:
        lines.append(_field("Summary", result.doc.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    body = result.body.rstrip("\n")
    if body:
        lines.extend((Text(""), Text(body)))
    return _render(lines)


@render_text.register
def render_doc_info(result: DocInfoResult) -> str:
    metadata = result.doc.metadata
    lines = [
        _title("Doc", result.doc.name),
        _field("Project", result.project.name),
        _field("Path", str(result.project.storage / result.doc.path), style=PATH),
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field("Modified", result.doc.modified_at.isoformat(), style=TIMESTAMP),
    ]
    if result.doc.summary:
        lines.append(_field("Summary", result.doc.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    return _render(lines)


@render_text.register
def render_doc_update(result: DocUpdateResult) -> str:
    line = Text("Updated doc ")
    line.append(result.doc.name, style=HEADING)
    line.append(f" in {result.project.name}")
    return _render([line])


@render_text.register
def render_task_show(result: TaskShowResult) -> str:
    metadata = result.task.metadata
    lines = [
        _title("Task", result.task.name, metadata.status),
        _field("Project", f"{result.project.name} / {result.plan}"),
        _field("Path", str(result.project.storage / result.task.path), style=PATH),
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field("Modified", result.task.modified_at.isoformat(), style=TIMESTAMP),
    ]
    if result.task.summary:
        lines.append(_field("Summary", result.task.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    body = result.body.rstrip("\n")
    if body:
        lines.extend((Text(""), Text(body)))
    return _render(lines)


@render_text.register
def render_show(result: PlanShowResult) -> str:
    metadata = result.plan.metadata
    lines = [
        _title("Plan", result.plan.name, metadata.status),
        _field("Project", f"{result.project.name} — {result.project.directory}"),
        _field("Path", str(result.project.storage / result.plan.path), style=PATH),
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field("Modified", result.plan.modified_at.isoformat(), style=TIMESTAMP),
    ]
    if result.plan.summary:
        lines.append(_field("Summary", result.plan.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    body = result.body.rstrip("\n")
    if body:
        lines.extend((Text(""), Text(body)))
    return _render(lines)


@render_text.register
def render_update(result: PlanUpdateResult) -> str:
    status = result.plan.metadata.status
    line = Text("Updated plan ")
    line.append(result.plan.name, style=HEADING)
    line.append(f" in {result.project.name} (")
    line.append(status, style=status_style(status))
    line.append(")")
    return _render([line])


@render_text.register
def render_select(result: PlanSelectResult) -> str:
    line = Text("Selected plan ")
    line.append(str(result.current_plan), style=HEADING)
    line.append(f" in {result.project.name}")
    return _render([line])


@render_text.register
def render_unselect(result: PlanUnselectResult) -> str:
    line = Text("Cleared the current plan in ")
    line.append(result.project.name, style=HEADING)
    return _render([line])


def _find_locator(entry: FindEntry) -> str:
    return entry.path.as_posix()


def _find_owner(entry: FindEntry) -> str:
    return f"[{entry.kind}{f' {entry.plan}' if entry.plan is not None else ''}]"


@render_text.register
def render_find(result: FindResult) -> str:
    scope = result.plan if result.plan is not None else "all plans"
    lines: list[RenderableType] = [Text(f"{result.project.name} / {scope}", style=PROJECT)]
    if not result.entries:
        lines.append(Text("No matches found.", style=MUTED))
        return _render(lines)
    ranked = any(entry.score is not None for entry in result.entries)
    lines.append(Text())
    table = Table.grid(padding=(0, 2))
    if ranked:
        table.add_column(justify="right", no_wrap=True, style=MUTED)
    table.add_column()
    for entry in result.entries:
        block = Text()
        block.append(_find_locator(entry), style=PATH)
        block.append("  ")
        block.append(_find_owner(entry), style=MUTED)
        score = f"{entry.score:.1f}" if entry.score is not None else ""
        if ranked:
            table.add_row(score, block)
        else:
            table.add_row(block)
    lines.append(table)
    return _render(lines)


@render_text.register
def render_instructions(result: InstructionsResult) -> str:
    return result.text


@render_text.register
def render_init(result: InitResult) -> str:
    lines = [
        Text(f"Initialized {result.project.name} at {result.project.directory}", style=HEADING),
        _field("Storage", str(result.project.storage), style=PATH),
    ]
    return _render(lines)


@render_text.register
def render_list(result: PlanListResult) -> str:
    lines = [
        Text(f"{result.project.name} — {result.project.directory}", style=PROJECT),
        _field("Storage", str(result.project.storage), style=PATH),
    ]
    if not result.plans:
        lines.append(Text("No plans found.", style=MUTED))
        return _render(lines)
    lines.append(Text())
    labels = [
        f"* {plan.name}" if plan.name == result.current_plan else plan.name for plan in result.plans
    ]
    name_width = max(len(label) for label in labels)
    tags = [", ".join(plan.metadata.tags) for plan in result.plans]
    tags_width = max((len(value) for value in tags), default=0)
    grouped = result.group_by is not None
    status_width = max((len(plan.metadata.status) for plan in result.plans), default=0)
    entries = [
        (
            plan.metadata.status,
            _entry(
                label,
                name_width,
                tag,
                tags_width,
                plan.summary,
                status=None if grouped else plan.metadata.status,
                status_width=status_width,
            ),
        )
        for plan, label, tag in zip(result.plans, labels, tags, strict=True)
    ]
    if grouped:
        lines.extend(_status_sections(entries, PLAN_STATUS_ORDER))
    else:
        lines.extend(row for _, row in entries)
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
