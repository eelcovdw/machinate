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


@dataclass
class Command:
    """A leaf CLI command: its name, handler, and result model."""

    name: str
    handler: Callable[..., None]
    result_model: type[BaseModel]


@dataclass
class CommandGroup:
    """A CLI command group: its name, help, and child commands."""

    name: str
    help: str
    children: tuple[Command | CommandGroup, ...]


type CommandEntry = Command | CommandGroup

COMMANDS: tuple[CommandEntry, ...] = (
    Command("init", init_command, InitResult),
    Command("info", info_command, InfoResult),
    Command("instructions", instructions_command, InstructionsResult),
    Command("search", search_command, SearchResult),
    CommandGroup(
        "plan",
        help="Manage plans; plan select sets the current plan used when the name is omitted.",
        children=(
            Command("add", plan_add_command, PlanAddResult),
            Command("info", plan_info_command, PlanInfoResult),
            Command("path", plan_path_command, PathResult),
            Command("list", plan_list_command, PlanListResult),
            Command("show", plan_show_command, PlanShowResult),
            Command("select", plan_select_command, PlanSelectResult),
            Command("unselect", plan_unselect_command, PlanUnselectResult),
            Command("update", plan_update_command, PlanUpdateResult),
        ),
    ),
    CommandGroup(
        "task",
        help="Manage tasks in a plan.",
        children=(
            Command("add", task_add_command, TaskAddResult),
            Command("info", task_info_command, TaskInfoResult),
            Command("path", task_path_command, PathResult),
            Command("list", task_list_command, TaskListResult),
            Command("show", task_show_command, TaskShowResult),
            Command("update", task_update_command, TaskUpdateResult),
        ),
    ),
    CommandGroup(
        "context",
        help="Manage context in a plan.",
        children=(
            Command("add", context_add_command, ContextAddResult),
            Command("info", context_info_command, ContextInfoResult),
            Command("path", context_path_command, PathResult),
            Command("list", context_list_command, ContextListResult),
            Command("show", context_show_command, ContextShowResult),
            Command("update", context_update_command, ContextUpdateResult),
        ),
    ),
    CommandGroup(
        "doc",
        help="Manage project-level docs.",
        children=(
            Command("add", doc_add_command, DocAddResult),
            Command("info", doc_info_command, DocInfoResult),
            Command("path", doc_path_command, PathResult),
            Command("list", doc_list_command, DocListResult),
            Command("show", doc_show_command, DocShowResult),
            Command("update", doc_update_command, DocUpdateResult),
        ),
    ),
)

# Hidden top-level conveniences that reuse an existing handler. Kept out of COMMANDS
# so they are neither listed in help nor emitted in the schema bundle.
ALIASES: tuple[Command, ...] = (Command("list", plan_list_command, PlanListResult),)


def leaves(
    specs: tuple[CommandEntry, ...] = COMMANDS, prefix: str = ""
) -> Iterator[tuple[str, Command]]:
    """Yield each leaf command with its space-separated command path, depth-first."""
    for spec in specs:
        path = f"{prefix} {spec.name}".strip()
        if isinstance(spec, CommandGroup):
            yield from leaves(spec.children, path)
        else:
            yield path, spec
