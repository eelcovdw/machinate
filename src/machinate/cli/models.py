from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from machinate.models.context import Context, ContextSummary
from machinate.models.plan import Plan, PlanOverview, PlanSummary, ProjectOverview
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


class TaskInfoResult(BaseModel):
    command: Literal["task info"] = "task info"
    project: ProjectScope
    plan: str
    task: TaskSummary


class TaskStatusResult(BaseModel):
    command: Literal["task status"] = "task status"
    project: ProjectScope
    plan: str
    task: Task


class ContextAddResult(BaseModel):
    command: Literal["context add"] = "context add"
    project: ProjectScope
    plan: str
    contexts: list[Context]


class ContextListResult(BaseModel):
    command: Literal["context list"] = "context list"
    project: ProjectScope
    plan: str
    contexts: list[ContextSummary]


class ContextShowResult(BaseModel):
    command: Literal["context show"] = "context show"
    project: ProjectScope
    plan: str
    context: Context


class ContextInfoResult(BaseModel):
    command: Literal["context info"] = "context info"
    project: ProjectScope
    plan: str
    context: ContextSummary


class InfoResult(BaseModel):
    command: Literal["info"] = "info"
    project: ProjectScope
    overview: ProjectOverview | PlanOverview = Field(discriminator="kind")


class ErrorResult(BaseModel):
    command: str = "list"
    error: str
    project: ProjectScope | None = None


type CommandResult = (
    AddResult
    | InfoResult
    | InitResult
    | ListResult
    | StatusResult
    | SetResult
    | ShowResult
    | TaskAddResult
    | TaskInfoResult
    | TaskListResult
    | TaskShowResult
    | TaskStatusResult
    | ContextAddResult
    | ContextInfoResult
    | ContextListResult
    | ContextShowResult
    | ErrorResult
)
