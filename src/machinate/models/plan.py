from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from machinate.models.update import DocumentUpdate
from machinate.storage.models import (
    Document,
    Name,
    PlanMetadata,
    PlanStatus,
    RelativePath,
    TaskStatus,
)
from machinate.storage.queries import DocumentRecord


class PlanUpdate(DocumentUpdate):
    status: PlanStatus = "draft"


class Plan(BaseModel):
    name: Name
    path: RelativePath
    document: Document[PlanMetadata]
    modified_at: datetime


class PlanInfo(BaseModel):
    plan: DocumentRecord[PlanMetadata]
    task_counts: dict[TaskStatus, int]
    context_count: int


class ProjectOverview(BaseModel):
    """Project-wide aggregates for `machi info` without an explicit plan."""

    kind: Literal["project"] = "project"
    current_plan: Name | None
    selection_valid: bool
    plan_count: int
    plans_by_status: dict[PlanStatus, int]
    task_totals: dict[TaskStatus, int]
    context_count: int
    recent_plans: list[DocumentRecord[PlanMetadata]]


class PlanOverview(BaseModel):
    """Plan-level overview for `machi plan info [-p NAME]`."""

    kind: Literal["plan"] = "plan"
    current: bool
    info: PlanInfo
