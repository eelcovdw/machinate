from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from machinate.storage.models import (
    Document,
    Name,
    PlanMetadata,
    PlanStatus,
    RelativePath,
    TaskStatus,
)
from machinate.storage.queries import DocumentRecord


class PlanUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    summary: str | None = None
    body: str = ""
    status: PlanStatus = "draft"


class Plan(BaseModel):
    name: Name
    path: RelativePath
    document: Document[PlanMetadata]
    modified_at: datetime


class PlanSummary(DocumentRecord[PlanMetadata]):
    pass


class PlanInfo(BaseModel):
    plan: PlanSummary
    task_counts: dict[TaskStatus, int]
    context_count: int
