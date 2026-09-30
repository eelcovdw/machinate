from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from machinate.models.documents import (
    ContextMetadata,
    DocMetadata,
    DocumentRecord,
    Name,
    PlanRecord,
    TaskMetadata,
)
from machinate.models.operations import (
    BatchCreated,
    ErrorCode,
    PlanOverview,
    ProjectOverview,
    SearchMatch,
    SearchSkip,
)


class ProjectScope(BaseModel):
    name: str
    directory: Path
    store_directory: Path


class InitResult(BaseModel):
    command: Literal["init"]
    project: ProjectScope


class PlanListResult(BaseModel):
    command: Literal["plan list"]
    project: ProjectScope
    plans: list[PlanRecord]
    current_plan: Name | None = None
    group_by: Literal["status"] | None = None


class PlanAddResult(BaseModel):
    command: Literal["plan add"]
    project: ProjectScope
    plan: PlanRecord


class PlanShowResult(BaseModel):
    command: Literal["plan show"]
    project: ProjectScope
    plan: PlanRecord
    body: str


class PlanSelectResult(BaseModel):
    command: Literal["plan select"]
    project: ProjectScope
    current_plan: Name | None


class PlanUnselectResult(BaseModel):
    command: Literal["plan unselect"]
    project: ProjectScope
    current_plan: Name | None


class PlanUpdateResult(BaseModel):
    command: Literal["plan update"]
    project: ProjectScope
    plan: PlanRecord
    body: str


class PlanInfoResult(BaseModel):
    command: Literal["plan info"]
    project: ProjectScope
    overview: PlanOverview


class TaskAddResult(BaseModel):
    command: Literal["task add"]
    project: ProjectScope
    plan_name: str
    batch: BatchCreated[DocumentRecord[TaskMetadata]]


class TaskListResult(BaseModel):
    command: Literal["task list"]
    project: ProjectScope
    plan_name: str
    tasks: list[DocumentRecord[TaskMetadata]]
    group_by: Literal["status"] | None = None


class TaskShowResult(BaseModel):
    command: Literal["task show"]
    project: ProjectScope
    plan_name: str
    task: DocumentRecord[TaskMetadata]
    body: str


class TaskInfoResult(BaseModel):
    command: Literal["task info"]
    project: ProjectScope
    plan_name: str
    task: DocumentRecord[TaskMetadata]


class TaskUpdateResult(BaseModel):
    command: Literal["task update"]
    project: ProjectScope
    plan_name: str
    task: DocumentRecord[TaskMetadata]
    body: str


class ContextAddResult(BaseModel):
    command: Literal["context add"]
    project: ProjectScope
    plan_name: str
    batch: BatchCreated[DocumentRecord[ContextMetadata]]


class ContextListResult(BaseModel):
    command: Literal["context list"]
    project: ProjectScope
    plan_name: str
    contexts: list[DocumentRecord[ContextMetadata]]


class ContextShowResult(BaseModel):
    command: Literal["context show"]
    project: ProjectScope
    plan_name: str
    context: DocumentRecord[ContextMetadata]
    body: str


class ContextInfoResult(BaseModel):
    command: Literal["context info"]
    project: ProjectScope
    plan_name: str
    context: DocumentRecord[ContextMetadata]


class ContextUpdateResult(BaseModel):
    command: Literal["context update"]
    project: ProjectScope
    plan_name: str
    context: DocumentRecord[ContextMetadata]
    body: str


class DocAddResult(BaseModel):
    command: Literal["doc add"]
    project: ProjectScope
    batch: BatchCreated[DocumentRecord[DocMetadata]]


class DocListResult(BaseModel):
    command: Literal["doc list"]
    project: ProjectScope
    docs: list[DocumentRecord[DocMetadata]]


class DocShowResult(BaseModel):
    command: Literal["doc show"]
    project: ProjectScope
    doc: DocumentRecord[DocMetadata]
    body: str


class DocInfoResult(BaseModel):
    command: Literal["doc info"]
    project: ProjectScope
    doc: DocumentRecord[DocMetadata]


class DocUpdateResult(BaseModel):
    command: Literal["doc update"]
    project: ProjectScope
    doc: DocumentRecord[DocMetadata]
    body: str


class PathResult(BaseModel):
    command: Literal["plan path", "task path", "context path", "doc path"]
    project: ProjectScope
    plan_name: str | None = None
    absolute_path: Path
    kind: Literal[
        "plan",
        "task",
        "context",
        "task_directory",
        "context_directory",
        "doc",
        "doc_directory",
    ]
    # Only meaningful for directory kinds; document paths are validated before rendering.
    exists: bool | None = None


class SearchResult(BaseModel):
    command: Literal["search"]
    project: ProjectScope
    plan_name: str | None = None
    query: str | None = None
    globs: list[str]
    matches: list[SearchMatch]
    skipped: list[SearchSkip] = Field(default_factory=list)


class InfoResult(BaseModel):
    command: Literal["info"]
    project: ProjectScope
    overview: ProjectOverview


class InstructionsResult(BaseModel):
    command: Literal["instructions"]
    text: str


class ErrorResult(BaseModel):
    command: str
    error: str
    code: ErrorCode
    project: ProjectScope | None = None


type CommandResult = (
    PlanAddResult
    | PlanInfoResult
    | PlanListResult
    | PlanSelectResult
    | PlanShowResult
    | PlanUnselectResult
    | PlanUpdateResult
    | SearchResult
    | InfoResult
    | InitResult
    | InstructionsResult
    | PathResult
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
    | ErrorResult
)
