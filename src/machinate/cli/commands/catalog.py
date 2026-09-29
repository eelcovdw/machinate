from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from machinate.cli.commands.contexts import (
    context_add,
    context_info,
    context_list,
    context_show,
    context_update,
)
from machinate.cli.commands.docs import (
    doc_add,
    doc_info,
    doc_list,
    doc_path,
    doc_show,
    doc_update,
)
from machinate.cli.commands.find import find_command
from machinate.cli.commands.instructions import instructions_command
from machinate.cli.commands.paths import context_path, plan_path, task_path
from machinate.cli.commands.plans import (
    add_plan,
    info_command,
    list_plans,
    plan_info_command,
    select_current_plan,
    show_plan,
    unselect_plan,
    update_plan,
)
from machinate.cli.commands.projects import init_project
from machinate.cli.commands.tasks import (
    task_add,
    task_info,
    task_list,
    task_show,
    update_task,
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


@dataclass(frozen=True)
class CommandSpec:
    """A CLI command or group: its name, handler, result model, or child commands."""

    name: str
    handler: Callable[..., None] | None = None
    result: type[BaseModel] | None = None
    children: tuple[CommandSpec, ...] = ()
    help: str | None = None

    def __post_init__(self) -> None:
        if bool(self.children) == (self.handler is not None):
            msg = f"{self.name!r}: define exactly one of handler or children"
            raise ValueError(msg)
        if self.handler is not None and self.result is None:
            msg = f"{self.name!r}: a command handler requires a result model"
            raise ValueError(msg)


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec("init", init_project, InitResult),
    CommandSpec("info", info_command, InfoResult),
    CommandSpec("instructions", instructions_command, InstructionsResult),
    CommandSpec("find", find_command, FindResult),
    CommandSpec(
        "plan",
        help="Manage plans; plan select sets the current plan used when -p is omitted.",
        children=(
            CommandSpec("add", add_plan, PlanAddResult),
            CommandSpec("info", plan_info_command, PlanInfoResult),
            CommandSpec("path", plan_path, PathResult),
            CommandSpec("list", list_plans, PlanListResult),
            CommandSpec("show", show_plan, PlanShowResult),
            CommandSpec("select", select_current_plan, PlanSelectResult),
            CommandSpec("unselect", unselect_plan, PlanUnselectResult),
            CommandSpec("update", update_plan, PlanUpdateResult),
        ),
    ),
    CommandSpec(
        "task",
        help="Manage tasks in a plan.",
        children=(
            CommandSpec("add", task_add, TaskAddResult),
            CommandSpec("info", task_info, TaskInfoResult),
            CommandSpec("path", task_path, PathResult),
            CommandSpec("list", task_list, TaskListResult),
            CommandSpec("show", task_show, TaskShowResult),
            CommandSpec("update", update_task, TaskUpdateResult),
        ),
    ),
    CommandSpec(
        "context",
        help="Manage context documents in a plan.",
        children=(
            CommandSpec("add", context_add, ContextAddResult),
            CommandSpec("info", context_info, ContextInfoResult),
            CommandSpec("path", context_path, PathResult),
            CommandSpec("list", context_list, ContextListResult),
            CommandSpec("show", context_show, ContextShowResult),
            CommandSpec("update", context_update, ContextUpdateResult),
        ),
    ),
    CommandSpec(
        "doc",
        help="Manage project-level documents.",
        children=(
            CommandSpec("add", doc_add, DocAddResult),
            CommandSpec("info", doc_info, DocInfoResult),
            CommandSpec("path", doc_path, PathResult),
            CommandSpec("list", doc_list, DocListResult),
            CommandSpec("show", doc_show, DocShowResult),
            CommandSpec("update", doc_update, DocUpdateResult),
        ),
    ),
)

# Hidden top-level conveniences that reuse an existing handler. Kept out of COMMANDS
# so they are neither listed in help nor emitted in the schema bundle.
ALIASES: tuple[CommandSpec, ...] = (CommandSpec("list", list_plans, PlanListResult),)
