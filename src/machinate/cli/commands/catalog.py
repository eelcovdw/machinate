from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from machinate.cli.commands.plans import add_plan, list_plans, set_plan, show_plan, status_plan
from machinate.cli.commands.projects import init_project
from machinate.cli.commands.tasks import status_task, task_add, task_list, task_show
from machinate.cli.models import (
    AddResult,
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
    CommandSpec("list", list_plans, ListResult),
    CommandSpec("show", show_plan, ShowResult),
    CommandSpec("set", set_plan, SetResult),
    CommandSpec("status", status_plan, StatusResult),
    CommandSpec(
        "task",
        children=(
            CommandSpec("add", task_add, TaskAddResult),
            CommandSpec("list", task_list, TaskListResult),
            CommandSpec("show", task_show, TaskShowResult),
            CommandSpec("status", status_task, TaskStatusResult),
        ),
    ),
)
