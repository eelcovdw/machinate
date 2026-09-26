from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from machinate.models.context import Context, ContextSummary
from machinate.models.plan import Plan, PlanOverview, PlanSummary, ProjectOverview
from machinate.models.task import Task, TaskSummary
from machinate.storage import ProjectState


class ProjectScope(BaseModel):
    name: str
    directory: Path
    storage: Path


class ListResult(BaseModel):
    command: Literal["plan list"] = "plan list"
    project: ProjectScope
    plans: list[PlanSummary]


class InitResult(BaseModel):
    command: Literal["init"] = "init"
    project: ProjectScope


class AddResult(BaseModel):
    command: Literal["plan add"] = "plan add"
    project: ProjectScope
    plan: Plan


class ShowResult(BaseModel):
    command: Literal["plan show"] = "plan show"
    project: ProjectScope
    plan: Plan


class SetResult(BaseModel):
    command: Literal["plan set"] = "plan set"
    project: ProjectScope
    state: ProjectState


class UpdateResult(BaseModel):
    command: Literal["plan update"] = "plan update"
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


class TaskUpdateResult(BaseModel):
    command: Literal["task update"] = "task update"
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


class ContextUpdateResult(BaseModel):
    command: Literal["context update"] = "context update"
    project: ProjectScope
    plan: str
    context: Context


class PathResult(BaseModel):
    command: Literal["plan path", "task path", "context path"]
    project: ProjectScope
    plan: str
    path: Path
    kind: Literal["plan", "task", "context", "tasks_directory", "context_directory"]
    exists: bool


class InfoResult(BaseModel):
    command: Literal["info"] = "info"
    project: ProjectScope
    overview: ProjectOverview


class InstructionsResult(BaseModel):
    command: Literal["instructions"] = "instructions"
    text: str


class PlanInfoResult(BaseModel):
    command: Literal["plan info"] = "plan info"
    project: ProjectScope
    overview: PlanOverview


class ErrorResult(BaseModel):
    command: str = "plan"
    error: str
    project: ProjectScope | None = None


type CommandResult = (
    AddResult
    | InfoResult
    | InitResult
    | ListResult
    | PlanInfoResult
    | PathResult
    | UpdateResult
    | SetResult
    | ShowResult
    | TaskAddResult
    | TaskInfoResult
    | TaskListResult
    | TaskShowResult
    | TaskUpdateResult
    | ContextAddResult
    | ContextInfoResult
    | ContextListResult
    | ContextShowResult
    | ContextUpdateResult
    | InstructionsResult
    | ErrorResult
)
