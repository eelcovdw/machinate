from datetime import datetime
from typing import ClassVar, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, PositiveInt, model_validator

from .models import Document, Metadata, PlanStatus, RelativePath, Tag, TaskStatus


class DocumentScope(BaseModel):
    path: RelativePath
    pattern: RelativePath


class DocumentCollection(DocumentScope):
    # Plans use their parent name; other documents keep collection-relative directories.
    name_source: Literal["parent", "stem"] = "stem"
    activity_scopes: tuple[DocumentScope, ...] = ()


type DocumentKind = Literal["plan", "task", "context", "doc", "unknown"]


class DocumentMembership(BaseModel):
    """Kind and owning plan/name for a storage-relative path."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: DocumentKind
    plan: str | None = None
    name: str | None = None


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

    @classmethod
    def from_document(
        cls,
        document: Document[M],
        *,
        name: str,
        path: RelativePath,
        last_activity_at: datetime,
    ) -> Self:
        """Summarize a loaded document as this domain summary type."""
        return cls.model_construct(
            name=name,
            path=path,
            metadata=document.metadata,
            last_activity_at=last_activity_at,
            summary=document.get_or_derive_summary(),
        )
