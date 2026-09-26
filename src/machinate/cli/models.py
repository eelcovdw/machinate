from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from machinate.models.plan import Plan, PlanSummary
from machinate.models.task import Task, TaskSummary
from machinate.storage import ProjectState


class ProjectScope(BaseModel):
    name: str
    directory: Path
    storage: Path


class ListResult(BaseModel):
    command: Literal["list"] = "list"
    project: ProjectScope
    plans: list[PlanSummary]


class InitResult(BaseModel):
    command: Literal["init"] = "init"
    project: ProjectScope


class AddResult(BaseModel):
    command: Literal["add"] = "add"
    project: ProjectScope
    plan: Plan


class ShowResult(BaseModel):
    command: Literal["show"] = "show"
    project: ProjectScope
    plan: Plan


class SetResult(BaseModel):
    command: Literal["set"] = "set"
    project: ProjectScope
    state: ProjectState


class StatusResult(BaseModel):
    command: Literal["status"] = "status"
    project: ProjectScope
    plan: Plan


class TaskAddResult(BaseModel):
    command: Literal["task add"] = "task add"
    project: ProjectScope
    plan: str
    tasks: list[Task]


class TaskListResult(BaseModel):
    command: Literal["task list"] = "task list"
    project: ProjectScope
    plan: str
    tasks: list[TaskSummary]


class TaskShowResult(BaseModel):
    command: Literal["task show"] = "task show"
    project: ProjectScope
    plan: str
    task: Task


class TaskStatusResult(BaseModel):
    command: Literal["task status"] = "task status"
    project: ProjectScope
    plan: str
    task: Task


class ErrorResult(BaseModel):
    command: str = "list"
    error: str
    project: ProjectScope | None = None


type CommandResult = (
    AddResult
    | InitResult
    | ListResult
    | StatusResult
    | SetResult
    | ShowResult
    | TaskAddResult
    | TaskListResult
    | TaskShowResult
    | TaskStatusResult
    | ErrorResult
)
