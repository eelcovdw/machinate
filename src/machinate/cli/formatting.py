import os
import shutil
import sys
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from io import StringIO
from typing import assert_never, get_args, override

from rich.console import Console, RenderableType
from rich.table import Table
from rich.text import Text

from machinate.models.documents import (
    DocumentRecord,
    Metadata,
    PlanRecord,
    PlanStatus,
    TaskStatus,
)
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


class Formatter(ABC):
    """Interface for command result formatters."""

    @abstractmethod
    def format(self, result: CommandResult) -> str:
        """Return the rendered form of a command result."""


class JsonFormatter(Formatter):
    """Emit pretty-printed JSON for every result, including errors."""

    @override
    def format(self, result: CommandResult) -> str:
        return result.model_dump_json(indent=2)


class TextFormatter(Formatter):
    """Emit human-readable text for every result."""

    @override
    def format(self, result: CommandResult) -> str:
        return render_text(result)


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
    lines.extend(_bullet(error.name, error.message, style=ERROR) for error in errors)
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


def _show[M: Metadata](  # noqa: PLR0913
    *,
    kind: str,
    record: DocumentRecord[M] | PlanRecord,
    location: str,
    path: str,
    status: str | None = None,
    modified_label: str = "Modified",
    modified: datetime | None = None,
    body: str | None = None,
) -> str:
    """Render one entity's title, location, timestamps, summary, tags, and optional body."""
    metadata = record.metadata
    lines: list[RenderableType] = [
        _title(kind, record.name, status),
        _field("Project", location),
        _field("Path", path, style=PATH),
        _field("Created", metadata.created_at.isoformat(), style=TIMESTAMP),
        _field(modified_label, (modified or record.modified_at).isoformat(), style=TIMESTAMP),
    ]
    if record.summary:
        lines.append(_field("Summary", record.summary))
    if metadata.tags:
        lines.append(_field("Tags", ", ".join(metadata.tags)))
    if body is not None and (stripped := body.rstrip("\n")):
        lines.extend((Text(""), Text(stripped)))
    return _render(lines)


def _add[M: Metadata](
    *,
    heading: str,
    records: Sequence[DocumentRecord[M] | PlanRecord],
    storage: str,
    errors: Sequence[BatchCreateError],
) -> str:
    """Render a batch creation heading, one bullet per record, and rejected names."""
    lines: list[RenderableType] = [Text(heading, style=HEADING)]
    lines.extend(_bullet(record.name, f"{storage}/{record.path}") for record in records)
    lines.extend(_not_created(errors))
    return _render(lines)


def _update(*, kind: str, name: str, location: str, status: str | None = None) -> str:
    line = Text(f"Updated {kind} ")
    line.append(name, style=HEADING)
    line.append(f" in {location}")
    if status is not None:
        line.append(" (")
        line.append(status, style=status_style(status))
        line.append(")")
    return _render([line])


def _list[M: Metadata](  # noqa: PLR0913
    *,
    header: Sequence[RenderableType],
    records: Sequence[DocumentRecord[M] | PlanRecord],
    empty_message: str,
    statuses: Sequence[str] | None = None,
    status_order: Sequence[str] = (),
    grouped: bool = False,
    current_plan: str | None = None,
) -> str:
    """Render a list header and its rows, optionally grouped under status headers."""
    lines = list(header)
    if not records:
        lines.append(Text(empty_message, style=MUTED))
        return _render(lines)
    lines.append(Text())
    labels = [
        f"* {record.name}"
        if current_plan is not None and record.name == current_plan
        else record.name
        for record in records
    ]
    name_width = max(len(label) for label in labels)
    tags = [", ".join(record.metadata.tags) for record in records]
    tags_width = max((len(value) for value in tags), default=0)
    status_width = (
        max((len(status) for status in statuses), default=0) if statuses is not None else 0
    )
    entries: list[tuple[str, Text]] = []
    for index, record in enumerate(records):
        status = statuses[index] if statuses is not None else None
        entries.append(
            (
                status or "",
                _entry(
                    labels[index],
                    name_width,
                    tags[index],
                    tags_width,
                    record.summary,
                    status=None if grouped else status,
                    status_width=status_width,
                ),
            )
        )
    if grouped:
        lines.extend(_status_sections(entries, status_order))
    else:
        lines.extend(row for _, row in entries)
    return _render(lines)


def render_text(result: CommandResult) -> str:  # noqa: C901, PLR0911, PLR0912
    """Render a command result as text; every result must have a renderer."""
    match result:
        case PlanAddResult():
            return render_plan_add(result)
        case PlanInfoResult():
            return render_plan_info(result)
        case PlanListResult():
            return render_plan_list(result)
        case PlanSelectResult():
            return render_plan_select(result)
        case PlanShowResult():
            return render_plan_show(result)
        case PlanUnselectResult():
            return render_plan_unselect(result)
        case PlanUpdateResult():
            return render_plan_update(result)
        case TaskAddResult():
            return render_task_add(result)
        case TaskInfoResult():
            return render_task_info(result)
        case TaskListResult():
            return render_task_list(result)
        case TaskShowResult():
            return render_task_show(result)
        case TaskUpdateResult():
            return render_task_update(result)
        case ContextAddResult():
            return render_context_add(result)
        case ContextInfoResult():
            return render_context_info(result)
        case ContextListResult():
            return render_context_list(result)
        case ContextShowResult():
            return render_context_show(result)
        case ContextUpdateResult():
            return render_context_update(result)
        case DocAddResult():
            return render_doc_add(result)
        case DocInfoResult():
            return render_doc_info(result)
        case DocListResult():
            return render_doc_list(result)
        case DocShowResult():
            return render_doc_show(result)
        case DocUpdateResult():
            return render_doc_update(result)
        case PathResult():
            return render_path(result)
        case FindResult():
            return render_find(result)
        case InfoResult():
            return render_info(result)
        case InitResult():
            return render_init(result)
        case InstructionsResult():
            return render_instructions(result)
        case ErrorResult():
            return render_error(result)
        case _:
            assert_never(result)


def render_error(result: ErrorResult) -> str:
    return _render([Text(f"Error: {result.error}", style=ERROR)])


def render_plan_add(result: PlanAddResult) -> str:
    return _add(
        heading=f"Created plan {result.plan.name} in {result.project.name}",
        records=[result.plan],
        storage=str(result.project.storage),
        errors=[],
    )


def render_plan_info(result: PlanInfoResult) -> str:
    overview = result.overview
    return _show(
        kind="Plan",
        record=overview.plan,
        location=f"{result.project.name} — {result.project.directory}",
        path=str(result.project.storage / overview.plan.path),
        status=overview.plan.metadata.status,
        modified_label="Last activity",
        modified=overview.plan.last_activity_at,
    )


def render_info(result: InfoResult) -> str:
    overview = result.overview
    current = overview.current_plan
    if current is not None and not overview.selection_valid:
        current = f"{current} (missing)"
    lines: list[RenderableType] = [
        Text(f"Project {result.project.name} — {result.project.directory}", style=PROJECT),
        _field("Storage", str(result.project.storage), style=PATH),
        _field("Current plan", current or "(none)", style="" if current else MUTED),
        _field("Plans", f"{overview.plan_count} ({_counts(overview.plans_by_status)})"),
        _field(
            "Tasks",
            f"{sum(overview.tasks_by_status.values())} ({_counts(overview.tasks_by_status)})",
        ),
        _field("Contexts", str(overview.context_count)),
        _field("Docs", str(overview.doc_count)),
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


def render_plan_list(result: PlanListResult) -> str:
    header: list[RenderableType] = [
        Text(f"{result.project.name} — {result.project.directory}", style=PROJECT),
        _field("Storage", str(result.project.storage), style=PATH),
    ]
    return _list(
        header=header,
        records=result.plans,
        empty_message="No plans found.",
        statuses=[plan.metadata.status for plan in result.plans],
        status_order=PLAN_STATUS_ORDER,
        grouped=result.group_by is not None,
        current_plan=result.current_plan,
    )


def render_plan_select(result: PlanSelectResult) -> str:
    return _update(kind="plan", name=str(result.current_plan), location=result.project.name)


def render_plan_show(result: PlanShowResult) -> str:
    return _show(
        kind="Plan",
        record=result.plan,
        location=f"{result.project.name} — {result.project.directory}",
        path=str(result.project.storage / result.plan.path),
        status=result.plan.metadata.status,
        body=result.body,
    )


def render_plan_unselect(result: PlanUnselectResult) -> str:
    line = Text("Cleared the current plan in ")
    line.append(result.project.name, style=HEADING)
    return _render([line])


def render_plan_update(result: PlanUpdateResult) -> str:
    return _update(
        kind="plan",
        name=result.plan.name,
        location=result.project.name,
        status=result.plan.metadata.status,
    )


def render_task_add(result: TaskAddResult) -> str:
    location = f"{result.project.name}/{result.plan}"
    return _add(
        heading=f"Created {len(result.batch.created)} task(s) in {location}",
        records=result.batch.created,
        storage=str(result.project.storage),
        errors=result.batch.errors,
    )


def render_task_info(result: TaskInfoResult) -> str:
    return _show(
        kind="Task",
        record=result.task,
        location=f"{result.project.name} / {result.plan}",
        path=str(result.project.storage / result.task.path),
        status=result.task.metadata.status,
    )


def render_task_list(result: TaskListResult) -> str:
    header = [Text(f"{result.project.name} / {result.plan}", style=PROJECT)]
    return _list(
        header=header,
        records=result.tasks,
        empty_message="No tasks found.",
        statuses=[task.metadata.status for task in result.tasks],
        status_order=TASK_STATUS_ORDER,
        grouped=result.group_by is not None,
        current_plan=None,
    )


def render_task_show(result: TaskShowResult) -> str:
    return _show(
        kind="Task",
        record=result.task,
        location=f"{result.project.name} / {result.plan}",
        path=str(result.project.storage / result.task.path),
        status=result.task.metadata.status,
        body=result.body,
    )


def render_task_update(result: TaskUpdateResult) -> str:
    return _update(
        kind="task",
        name=result.task.name,
        location=f"{result.project.name}/{result.plan}",
        status=result.task.metadata.status,
    )


def render_context_add(result: ContextAddResult) -> str:
    location = f"{result.project.name}/{result.plan}"
    return _add(
        heading=f"Created {len(result.batch.created)} context document(s) in {location}",
        records=result.batch.created,
        storage=str(result.project.storage),
        errors=result.batch.errors,
    )


def render_context_info(result: ContextInfoResult) -> str:
    return _show(
        kind="Context",
        record=result.context,
        location=f"{result.project.name} / {result.plan}",
        path=str(result.project.storage / result.context.path),
    )


def render_context_list(result: ContextListResult) -> str:
    header = [Text(f"{result.project.name} / {result.plan}", style=PROJECT)]
    return _list(
        header=header,
        records=result.contexts,
        empty_message="No contexts found.",
    )


def render_context_show(result: ContextShowResult) -> str:
    return _show(
        kind="Context",
        record=result.context,
        location=f"{result.project.name} / {result.plan}",
        path=str(result.project.storage / result.context.path),
        body=result.body,
    )


def render_context_update(result: ContextUpdateResult) -> str:
    return _update(
        kind="context",
        name=result.context.name,
        location=f"{result.project.name}/{result.plan}",
    )


def render_doc_add(result: DocAddResult) -> str:
    return _add(
        heading=f"Created {len(result.batch.created)} document(s) in {result.project.name}",
        records=result.batch.created,
        storage=str(result.project.storage),
        errors=result.batch.errors,
    )


def render_doc_info(result: DocInfoResult) -> str:
    return _show(
        kind="Doc",
        record=result.doc,
        location=result.project.name,
        path=str(result.project.storage / result.doc.path),
    )


def render_doc_list(result: DocListResult) -> str:
    header = [Text(result.project.name, style=PROJECT)]
    return _list(
        header=header,
        records=result.docs,
        empty_message="No documents found.",
    )


def render_doc_show(result: DocShowResult) -> str:
    return _show(
        kind="Doc",
        record=result.doc,
        location=result.project.name,
        path=str(result.project.storage / result.doc.path),
        body=result.body,
    )


def render_doc_update(result: DocUpdateResult) -> str:
    return _update(kind="doc", name=result.doc.name, location=result.project.name)


def render_path(result: PathResult) -> str:
    return str(result.path)


def _find_locator(entry: FindEntry) -> str:
    return entry.path.as_posix()


def _find_owner(entry: FindEntry) -> str:
    return f"[{entry.kind}{f' {entry.plan}' if entry.plan is not None else ''}]"


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


def render_instructions(result: InstructionsResult) -> str:
    return result.text


def render_init(result: InitResult) -> str:
    lines: list[RenderableType] = [
        Text(f"Initialized {result.project.name} at {result.project.directory}", style=HEADING),
        _field("Storage", str(result.project.storage), style=PATH),
    ]
    return _render(lines)


class UnknownFormatError(Exception):
    pass


def select_formatter(name: str, formatters: Mapping[str, Formatter]) -> Formatter:
    try:
        return formatters[name]
    except KeyError as exc:
        message = f"Unknown format {name!r}. Available formats: {', '.join(formatters)}"
        raise UnknownFormatError(message) from exc
