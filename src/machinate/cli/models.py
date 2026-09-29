from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from machinate.models.documents import (
    ContextMetadata,
    DocMetadata,
    DocumentRecord,
    Name,
    PlanRecord,
    TaskMetadata,
)
from machinate.models.operations import BatchCreateError, FindEntry, PlanOverview, ProjectOverview


class ProjectScope(BaseModel):
    name: str
    directory: Path
    storage: Path


class ListResult(BaseModel):
    command: Literal["plan list"] = "plan list"
    project: ProjectScope
    plans: list[PlanRecord]
    current_plan: Name | None = None
    group_by: Literal["status"] | None = None


class InitResult(BaseModel):
    command: Literal["init"] = "init"
    project: ProjectScope


class AddResult(BaseModel):
    command: Literal["plan add"] = "plan add"
    project: ProjectScope
    plan: PlanRecord
    body: str


class ShowResult(BaseModel):
    command: Literal["plan show"] = "plan show"
    project: ProjectScope
    plan: PlanRecord
    body: str


class SelectResult(BaseModel):
    command: Literal["plan select"] = "plan select"
    project: ProjectScope
    current_plan: Name | None


class UnselectResult(BaseModel):
    command: Literal["plan unselect"] = "plan unselect"
    project: ProjectScope
    current_plan: Name | None


class UpdateResult(BaseModel):
    command: Literal["plan update"] = "plan update"
    project: ProjectScope
    plan: PlanRecord
    body: str


class TaskAddResult(BaseModel):
    command: Literal["task add"] = "task add"
    project: ProjectScope
    plan: str
    tasks: list[DocumentRecord[TaskMetadata]]
    body: str
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
    task: DocumentRecord[TaskMetadata]
    body: str


class TaskInfoResult(BaseModel):
    command: Literal["task info"] = "task info"
    project: ProjectScope
    plan: str
    task: DocumentRecord[TaskMetadata]


class TaskUpdateResult(BaseModel):
    command: Literal["task update"] = "task update"
    project: ProjectScope
    plan: str
    task: DocumentRecord[TaskMetadata]
    body: str


class ContextAddResult(BaseModel):
    command: Literal["context add"] = "context add"
    project: ProjectScope
    plan: str
    contexts: list[DocumentRecord[ContextMetadata]]
    body: str
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
    context: DocumentRecord[ContextMetadata]
    body: str


class ContextInfoResult(BaseModel):
    command: Literal["context info"] = "context info"
    project: ProjectScope
    plan: str
    context: DocumentRecord[ContextMetadata]


class ContextUpdateResult(BaseModel):
    command: Literal["context update"] = "context update"
    project: ProjectScope
    plan: str
    context: DocumentRecord[ContextMetadata]
    body: str


class DocAddResult(BaseModel):
    command: Literal["doc add"] = "doc add"
    project: ProjectScope
    docs: list[DocumentRecord[DocMetadata]]
    body: str
    errors: list[BatchCreateError] = []


class DocListResult(BaseModel):
    command: Literal["doc list"] = "doc list"
    project: ProjectScope
    docs: list[DocumentRecord[DocMetadata]]


class DocShowResult(BaseModel):
    command: Literal["doc show"] = "doc show"
    project: ProjectScope
    doc: DocumentRecord[DocMetadata]
    body: str


class DocInfoResult(BaseModel):
    command: Literal["doc info"] = "doc info"
    project: ProjectScope
    doc: DocumentRecord[DocMetadata]


class DocUpdateResult(BaseModel):
    command: Literal["doc update"] = "doc update"
    project: ProjectScope
    doc: DocumentRecord[DocMetadata]
    body: str


class PathResult(BaseModel):
    command: Literal["plan path", "task path", "context path", "doc path"]
    project: ProjectScope
    plan: str | None = None
    path: Path
    kind: Literal[
        "plan",
        "task",
        "context",
        "tasks_directory",
        "context_directory",
        "doc",
        "docs_directory",
    ]
    # Only meaningful for directory kinds; document paths are validated before rendering.
    exists: bool | None = None


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
    | DocAddResult
    | DocInfoResult
    | DocListResult
    | DocShowResult
    | DocUpdateResult
    | InstructionsResult
    | ErrorResult
)
