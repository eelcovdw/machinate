"""Operation models: create inputs, update models, queries, search, batch
results, and overview aggregates.

Models are ordered top-down by dependency: create inputs, updates, queries,
search, batch results, then overviews.
"""

# --- Create inputs ---------------------------------------------------------

from typing import ClassVar, Literal, override

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

from .documents import (
    DocumentMembership,
    Metadata,
    Name,
    ParsedDocument,
    PlanRecord,
    PlanStatus,
    RelativePath,
    StatusMetadata,
    Tag,
    TaskStatus,
    validate_relative_path,
)


class CreateInput(BaseModel):
    """The fields a caller may set at creation time; the service supplies the rest."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    summary: str | None = None
    tags: list[Tag] = Field(default_factory=list)


class StatusCreateInput[S: str](CreateInput):
    status: S | None = None


# --- Update models ---------------------------------------------------------


class DocumentUpdate(BaseModel):
    """Fields a document update may change; subclasses add domain-specific ones."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    summary: str | None = None
    tags: list[Tag] | None = None

    def apply_to[M: Metadata](self, document: ParsedDocument[M]) -> ParsedDocument[M] | None:
        """Return a document with this update applied, or None when nothing changed.

        Only fields explicitly set are considered; an update whose values already
        match the document reports no change, so the file is not rewritten.
        """
        updates = self._proposed_updates(document)
        if not updates:
            return None
        metadata = document.metadata.model_copy(update=updates)
        return document.model_copy(update={"metadata": metadata})

    def _proposed_updates[M: Metadata](self, document: ParsedDocument[M]) -> dict[str, object]:
        """Metadata fields this update would change, keyed by field name."""
        updates: dict[str, object] = {}
        if "summary" in self.model_fields_set:
            summary = self.summary or None
            if summary != document.metadata.summary:
                updates["summary"] = summary
        if "tags" in self.model_fields_set:
            proposed_tags = self.tags if self.tags is not None else []
            if proposed_tags != document.metadata.tags:
                updates["tags"] = proposed_tags
        return updates


class StatusUpdate[S: str](DocumentUpdate):
    """An update that may change a status; an unset status leaves it unchanged."""

    status: S | None = None

    @override
    def _proposed_updates[M: Metadata](self, document: ParsedDocument[M]) -> dict[str, object]:
        updates = super()._proposed_updates(document)
        metadata = document.metadata
        if (
            "status" in self.model_fields_set
            and isinstance(metadata, StatusMetadata)
            and not metadata.status_matches(self.status)
        ):
            updates["status"] = self.status
        return updates


# --- Queries ---------------------------------------------------------------


class DocumentQuery(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    #: Sort keys valid for task, context, and doc listings.
    _allowed_sorts: ClassVar[frozenset[str]] = frozenset({"name", "created_at", "modified_at"})

    tags: set[Tag] | None = None
    sort: Literal["name", "created_at", "modified_at", "last_activity_at"] = "name"
    descending: bool = False
    limit: PositiveInt | None = None

    @field_validator("sort")
    @classmethod
    def _validate_sort(cls, value: str) -> str:
        if value not in cls._allowed_sorts:
            raise ValueError("Sort key is not supported for this document kind")
        return value

    def matches(self, metadata: Metadata) -> bool:
        """Return whether a document's metadata satisfies this query's filters."""
        if self.tags is not None:
            document_tags = {tag.casefold() for tag in metadata.tags}
            if document_tags.isdisjoint(tag.casefold() for tag in self.tags):
                return False
        return True


class StatusQuery[S: str](DocumentQuery):
    statuses: set[S] | None = None

    @override
    def matches(self, metadata: Metadata) -> bool:
        if not super().matches(metadata):
            return False
        if self.statuses is None:
            return True
        status = getattr(metadata, "status", None)
        return status in self.statuses


class PlanQuery(StatusQuery[PlanStatus]):
    """Plan listing filters; plans are the one kind that can sort by activity."""

    _allowed_sorts: ClassVar[frozenset[str]] = frozenset(
        {"name", "created_at", "modified_at", "last_activity_at"}
    )


class TaskQuery(StatusQuery[TaskStatus]):
    pass


# --- Search ----------------------------------------------------------------

DEFAULT_GLOB = "**/*.md"


class FindQuery(BaseModel):
    """Criteria for a filesystem-level search under the project store.

    ``query`` is a tantivy query string: terms, ``"phrases"``, ``field:term``, ``+``/``-``,
    ``AND``/``OR``, ``^boost``, ranges and set terms. Fuzzy (one-typo, prefix) matching is
    on by default; ``exact`` turns it off. Regex terms need ``regex`` and a field prefix.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query: str | None = None
    globs: list[str] = Field(default_factory=list)
    plan: Name | None = None
    limit: PositiveInt | None = None
    regex: bool = False
    exact: bool = False

    @field_validator("globs")
    @classmethod
    def _validate_globs(cls, globs: list[str]) -> list[str]:
        """Reject absolute or parent-relative globs at the edge; keep the pattern text."""
        for glob in globs:
            validate_relative_path(glob)
        return globs


class FindEntry(DocumentMembership):
    """A matched file with its storage-relative path and plan/task/context membership.

    ``score`` is the tantivy BM25 relevance; it is only set for query searches and is
    meaningful relative to the other entries of the same query, not as an absolute score.
    """

    path: RelativePath
    score: float | None = None


# --- Batch results ---------------------------------------------------------


class BatchCreateError(BaseModel):
    """A name from a batch creation that was not created, with the reason."""

    name: str
    error: str


class BatchCreated[T](BaseModel):
    """The outcome of a batch creation: created documents and per-name failures."""

    created: list[T]
    errors: list[BatchCreateError]


# --- Overviews -------------------------------------------------------------


class PlanOverview(BaseModel):
    """Plan-level overview for `machi plan info [-p NAME]`."""

    current: bool
    plan: PlanRecord
    tasks_by_status: dict[TaskStatus, int]
    context_count: int


class ProjectOverview(BaseModel):
    """Project-wide aggregates for `machi info` without an explicit plan."""

    current_plan: Name | None
    selection_valid: bool
    plan_count: int
    plans_by_status: dict[PlanStatus, int]
    tasks_by_status: dict[TaskStatus, int]
    context_count: int
    recent_plans: list[PlanRecord]
