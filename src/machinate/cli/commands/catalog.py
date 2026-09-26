from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from machinate.cli.commands.contexts import (
    context_add,
    context_info,
    context_list,
    context_show,
)
from machinate.cli.commands.paths import context_path, plan_path, task_path
from machinate.cli.commands.plans import (
    add_plan,
    info_command,
    list_plans,
    set_plan,
    show_plan,
    status_plan,
)
from machinate.cli.commands.projects import init_project
from machinate.cli.commands.tasks import (
    status_task,
    task_add,
    task_info,
    task_list,
    task_show,
)
from machinate.cli.models import (
    AddResult,
    ContextAddResult,
    ContextInfoResult,
    ContextListResult,
    ContextShowResult,
    InfoResult,
    InitResult,
    ListResult,
    PathResult,
    SetResult,
    ShowResult,
    StatusResult,
    TaskAddResult,
    TaskInfoResult,
    TaskListResult,
    TaskShowResult,
    TaskStatusResult,
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
    CommandSpec("add", add_plan, AddResult),
    CommandSpec("info", info_command, InfoResult),
    CommandSpec("path", plan_path, PathResult),
    CommandSpec("list", list_plans, ListResult),
    CommandSpec("show", show_plan, ShowResult),
    CommandSpec("set", set_plan, SetResult),
    CommandSpec("status", status_plan, StatusResult),
    CommandSpec(
        "task",
        children=(
            CommandSpec("add", task_add, TaskAddResult),
            CommandSpec("info", task_info, TaskInfoResult),
            CommandSpec("path", task_path, PathResult),
            CommandSpec("list", task_list, TaskListResult),
            CommandSpec("show", task_show, TaskShowResult),
            CommandSpec("status", status_task, TaskStatusResult),
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
        ),
    ),
)
