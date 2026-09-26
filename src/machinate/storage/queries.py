from datetime import datetime
from typing import ClassVar, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, PositiveInt, model_validator

from .models import Metadata, PlanStatus, RelativePath, Tag, TaskStatus


class DocumentScope(BaseModel):
    path: RelativePath
    pattern: RelativePath


class DocumentCollection(DocumentScope):
    # Plans use their parent name; other documents keep collection-relative directories.
    name_source: Literal["parent", "stem"] = "stem"
    activity_scopes: tuple[DocumentScope, ...] = ()


class DateTimeRange(BaseModel):
    """Inclusive timezone-aware timestamp bounds."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    gte: AwareDatetime | None = None
    lte: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if self.gte is not None and self.lte is not None and self.gte > self.lte:
            raise ValueError("gte must not be after lte")
        return self


class DocumentQuery(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    search: str | None = None
    search_body: bool = False
    tags: set[Tag] | None = None
    created_range: DateTimeRange | None = None
    updated_range: DateTimeRange | None = None
    sort: Literal["name", "created", "updated"] = "name"
    descending: bool = False
    limit: PositiveInt | None = None


class StatusQuery[S: str](DocumentQuery):
    statuses: set[S] | None = None


class PlanQuery(StatusQuery[PlanStatus]):
    pass


class TaskQuery(StatusQuery[TaskStatus]):
    pass


class DocumentRecord[M: Metadata](BaseModel):
    name: str
    path: RelativePath
    metadata: M
    last_activity_at: datetime
    # Effective summary: the authored one, otherwise derived from the body.
    summary: str | None = None
