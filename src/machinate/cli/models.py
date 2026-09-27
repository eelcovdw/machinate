from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from machinate.models.batch import BatchCreateError
from machinate.models.context import Context
from machinate.models.plan import Plan, PlanOverview, ProjectOverview
from machinate.models.search import FindEntry
from machinate.models.task import Task
from machinate.storage import DocumentRecord, ProjectState
from machinate.storage.models import ContextMetadata, PlanMetadata, TaskMetadata


class ProjectScope(BaseModel):
    name: str
    directory: Path
    storage: Path


class ListResult(BaseModel):
    command: Literal["plan list"] = "plan list"
    project: ProjectScope
    plans: list[DocumentRecord[PlanMetadata]]
    group_by: Literal["status"] | None = None


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


class SelectResult(BaseModel):
    command: Literal["plan select"] = "plan select"
    project: ProjectScope
    state: ProjectState


class UnselectResult(BaseModel):
    command: Literal["plan unselect"] = "plan unselect"
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
    errors: list[BatchCreateError] = []


class TaskListResult(BaseModel):
    command: Literal["task list"] = "task list"
    project: ProjectScope
    plan: str
    tasks: list[DocumentRecord[TaskMetadata]]
    group_by: Literal["status"] | None = None


class TaskShowResult(BaseModel):
    command: Literal["task show"] = "task show"
    project: ProjectScope
    plan: str
    task: Task


class TaskInfoResult(BaseModel):
    command: Literal["task info"] = "task info"
    project: ProjectScope
    plan: str
    task: DocumentRecord[TaskMetadata]


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
    errors: list[BatchCreateError] = []


class ContextListResult(BaseModel):
    command: Literal["context list"] = "context list"
    project: ProjectScope
    plan: str
    contexts: list[DocumentRecord[ContextMetadata]]


class ContextShowResult(BaseModel):
    command: Literal["context show"] = "context show"
    project: ProjectScope
    plan: str
    context: Context


class ContextInfoResult(BaseModel):
    command: Literal["context info"] = "context info"
    project: ProjectScope
    plan: str
    context: DocumentRecord[ContextMetadata]


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


class FindResult(BaseModel):
    command: Literal["find"] = "find"
    project: ProjectScope
    plan: str | None = None
    query: str | None = None
    globs: list[str]
    entries: list[FindEntry]


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
    | FindResult
    | InfoResult
    | InitResult
    | ListResult
    | PlanInfoResult
    | PathResult
    | UpdateResult
    | SelectResult
    | UnselectResult
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
