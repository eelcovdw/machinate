from datetime import datetime

from pydantic import BaseModel

from machinate.models.update import DocumentUpdate
from machinate.storage.models import (
    Document,
    RelativePath,
    TaskMetadata,
    TaskName,
    TaskStatus,
)


class TaskUpdate(DocumentUpdate):
    status: TaskStatus = "todo"


class Task(BaseModel):
    name: TaskName
    path: RelativePath
    document: Document[TaskMetadata]
    modified_at: datetime
