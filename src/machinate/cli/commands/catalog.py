from collections.abc import Callable, Iterator
from dataclasses import dataclass

from pydantic import BaseModel

from machinate.cli.commands.contexts import (
    context_add_command,
    context_info_command,
    context_list_command,
    context_path_command,
    context_show_command,
    context_update_command,
)
from machinate.cli.commands.docs import (
    doc_add_command,
    doc_info_command,
    doc_list_command,
    doc_path_command,
    doc_show_command,
    doc_update_command,
)
from machinate.cli.commands.instructions import instructions_command
from machinate.cli.commands.plans import (
    plan_add_command,
    plan_info_command,
    plan_list_command,
    plan_path_command,
    plan_select_command,
    plan_show_command,
    plan_unselect_command,
    plan_update_command,
)
from machinate.cli.commands.projects import info_command, init_command
from machinate.cli.commands.search import search_command
from machinate.cli.commands.tasks import (
    task_add_command,
    task_info_command,
    task_list_command,
    task_path_command,
    task_show_command,
    task_update_command,
)
from machinate.cli.models import (
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
    SearchResult,
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskUpdateResult,
)


@dataclass(frozen=True)
class CommandSpec:
    """A CLI command or group: its name, handler, result model, or child commands."""

    name: str
    handler: Callable[..., None] | None = None
    result_model: type[BaseModel] | None = None
    children: tuple[CommandSpec, ...] = ()
    help: str | None = None

    def __post_init__(self) -> None:
        if bool(self.children) == (self.handler is not None):
            msg = f"{self.name!r}: define exactly one of handler or children"
            raise ValueError(msg)
        if self.handler is not None and self.result_model is None:
            msg = f"{self.name!r}: a command handler requires a result model"
            raise ValueError(msg)


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("init", init_command, InitResult),
    CommandSpec("info", info_command, InfoResult),
    CommandSpec("instructions", instructions_command, InstructionsResult),
    CommandSpec("search", search_command, SearchResult),
    CommandSpec(
        "plan",
        help="Manage plans; plan select sets the current plan used when -p is omitted.",
        children=(
            CommandSpec("add", plan_add_command, PlanAddResult),
            CommandSpec("info", plan_info_command, PlanInfoResult),
            CommandSpec("path", plan_path_command, PathResult),
            CommandSpec("list", plan_list_command, PlanListResult),
            CommandSpec("show", plan_show_command, PlanShowResult),
            CommandSpec("select", plan_select_command, PlanSelectResult),
            CommandSpec("unselect", plan_unselect_command, PlanUnselectResult),
            CommandSpec("update", plan_update_command, PlanUpdateResult),
        ),
    ),
    CommandSpec(
        "task",
        help="Manage tasks in a plan.",
        children=(
            CommandSpec("add", task_add_command, TaskAddResult),
            CommandSpec("info", task_info_command, TaskInfoResult),
            CommandSpec("path", task_path_command, PathResult),
            CommandSpec("list", task_list_command, TaskListResult),
            CommandSpec("show", task_show_command, TaskShowResult),
            CommandSpec("update", task_update_command, TaskUpdateResult),
        ),
    ),
    CommandSpec(
        "context",
        help="Manage context in a plan.",
        children=(
            CommandSpec("add", context_add_command, ContextAddResult),
            CommandSpec("info", context_info_command, ContextInfoResult),
            CommandSpec("path", context_path_command, PathResult),
            CommandSpec("list", context_list_command, ContextListResult),
            CommandSpec("show", context_show_command, ContextShowResult),
            CommandSpec("update", context_update_command, ContextUpdateResult),
        ),
    ),
    CommandSpec(
        "doc",
        help="Manage project-level docs.",
        children=(
            CommandSpec("add", doc_add_command, DocAddResult),
            CommandSpec("info", doc_info_command, DocInfoResult),
            CommandSpec("path", doc_path_command, PathResult),
            CommandSpec("list", doc_list_command, DocListResult),
            CommandSpec("show", doc_show_command, DocShowResult),
            CommandSpec("update", doc_update_command, DocUpdateResult),
        ),
    ),
)

# Hidden top-level conveniences that reuse an existing handler. Kept out of COMMANDS
# so they are neither listed in help nor emitted in the schema bundle.
ALIASES: tuple[CommandSpec, ...] = (CommandSpec("list", plan_list_command, PlanListResult),)


def leaves(
    specs: tuple[CommandSpec, ...] = COMMANDS, prefix: str = ""
) -> Iterator[tuple[str, CommandSpec]]:
    """Yield each leaf command with its space-separated command path, depth-first."""
    for spec in specs:
        path = f"{prefix} {spec.name}".strip()
        if spec.children:
            yield from leaves(spec.children, path)
        else:
            yield path, spec
