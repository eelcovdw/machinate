from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from machinate.storage.models import (
    Document,
    Name,
    PlanMetadata,
    PlanStatus,
    RelativePath,
    Tag,
    TaskStatus,
)
from machinate.storage.queries import DocumentRecord


class PlanUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    body: str = ""
    status: PlanStatus = "draft"
    summary: str | None = None
    tags: list[Tag] | None = None


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


class ProjectOverview(BaseModel):
    """Project-wide aggregates for `machi info` without an explicit plan."""

    kind: Literal["project"] = "project"
    current_plan: Name | None
    selection_valid: bool
    plan_count: int
    plans_by_status: dict[PlanStatus, int]
    task_totals: dict[TaskStatus, int]
    context_count: int
    recent_plans: list[PlanSummary]


class PlanOverview(BaseModel):
    """Plan-level overview for `machi plan info [-p NAME]`."""

    kind: Literal["plan"] = "plan"
    current: bool
    info: PlanInfo
