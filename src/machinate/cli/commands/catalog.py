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
from machinate.cli.commands.find import find_command
from machinate.cli.commands.instructions import instructions_command
from machinate.cli.commands.paths import context_path, plan_path, task_path
from machinate.cli.commands.plans import (
    add_plan,
    info_command,
    list_plans,
    plan_info_command,
    set_plan,
    show_plan,
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
    AddResult,
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    ContextUpdateResult,
    FindResult,
    InfoResult,
    InitResult,
    InstructionsResult,
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


@dataclass(frozen=True)
class CommandSpec:
    """A CLI command or group: its name, handler, result model, or child commands."""

    name: str
    handler: Callable[..., None] | None = None
    result: type[BaseModel] | None = None
    children: tuple[CommandSpec, ...] = ()

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
        children=(
            CommandSpec("add", add_plan, AddResult),
            CommandSpec("info", plan_info_command, PlanInfoResult),
            CommandSpec("path", plan_path, PathResult),
            CommandSpec("list", list_plans, ListResult),
            CommandSpec("show", show_plan, ShowResult),
            CommandSpec("set", set_plan, SetResult),
            CommandSpec("update", update_plan, UpdateResult),
        ),
    ),
    CommandSpec(
        "task",
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
        children=(
            CommandSpec("add", context_add, ContextAddResult),
            CommandSpec("info", context_info, ContextInfoResult),
            CommandSpec("path", context_path, PathResult),
            CommandSpec("list", context_list, ContextListResult),
            CommandSpec("show", context_show, ContextShowResult),
            CommandSpec("update", context_update, ContextUpdateResult),
        ),
    ),
)

# Hidden top-level conveniences that reuse an existing handler. Kept out of COMMANDS
# so they are neither listed in help nor emitted in the schema bundle.
ALIASES: tuple[CommandSpec, ...] = (CommandSpec("list", list_plans, ListResult),)
