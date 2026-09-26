from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from machinate.storage.models import (
    Document,
    RelativePath,
    Tag,
    TaskMetadata,
    TaskName,
    TaskStatus,
)
from machinate.storage.queries import DocumentRecord


class TaskUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    body: str = ""
    status: TaskStatus = "todo"
    summary: str | None = None
    tags: list[Tag] | None = None


class Task(BaseModel):
    name: TaskName
    path: RelativePath
    document: Document[TaskMetadata]
    modified_at: datetime


class TaskSummary(DocumentRecord[TaskMetadata]):
    pass
