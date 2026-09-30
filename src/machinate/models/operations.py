"""Operation models: create inputs, update models, queries, search, batch
results, and overview aggregates.

Models are ordered top-down by dependency: create inputs, updates, queries,
search, batch results, then overviews.
"""

# --- Create inputs ---------------------------------------------------------

from typing import ClassVar, Literal, TypeGuard, override

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

from .documents import (
    DocumentIdentity,
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


def _has_status(metadata: Metadata) -> TypeGuard[StatusMetadata[str]]:
    """Narrow metadata to a document kind that stores a status."""
    return isinstance(metadata, StatusMetadata)


# --- Error codes -----------------------------------------------------------

type ErrorCode = Literal[
    "input",
    "not_found",
    "exists",
    "invalid_document",
    "search_query",
    "storage",
    "project",
    "internal",
]


class CreateInput(BaseModel):
    """The fields a caller may set at creation time; the service supplies the rest."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    summary: str | None = None
    tags: list[Tag] = Field(default_factory=list)


class StatusCreateInput[S: str](CreateInput):
    status: S | None = None


# --- Update models ---------------------------------------------------------


def _apply_updates[M: Metadata](
    updates: dict[str, object], document: ParsedDocument[M]
) -> ParsedDocument[M] | None:
    """Return a document with the proposed metadata updates, or None when unchanged."""
    if not updates:
        return None
    metadata = document.metadata.model_copy(update=updates)
    return document.model_copy(update={"metadata": metadata})


def _summary_tag_updates[M: Metadata](
    document: ParsedDocument[M],
    *,
    summary: str | None,
    tags: list[Tag] | None,
    fields_set: set[str],
) -> dict[str, object]:
    """The summary/tag fields an update would change, keyed by field name."""
    updates: dict[str, object] = {}
    if "summary" in fields_set:
        proposed_summary = summary or None
        if proposed_summary != document.metadata.summary:
            updates["summary"] = proposed_summary
    if "tags" in fields_set:
        proposed_tags = tags if tags is not None else []
        if proposed_tags != document.metadata.tags:
            updates["tags"] = proposed_tags
    return updates


class DocumentUpdate(BaseModel):
    """Summary and tag changes for a document that has no status."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    summary: str | None = None
    tags: list[Tag] | None = None

    def apply_to[M: Metadata](self, document: ParsedDocument[M]) -> ParsedDocument[M] | None:
        """Return a document with this update applied, or None when nothing changed."""
        updates = _summary_tag_updates(
            document, summary=self.summary, tags=self.tags, fields_set=self.model_fields_set
        )
        return _apply_updates(updates, document)


class StatusUpdate[S: str](BaseModel):
    """Summary, tag, and status changes for a document that has a status.

    This is deliberately not a ``DocumentUpdate``: a status update can only reach a
    service whose documents have a status. An unset status leaves it unchanged.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", validate_assignment=True)

    summary: str | None = None
    tags: list[Tag] | None = None
    status: S | None = None

    def apply_to[M: Metadata](self, document: ParsedDocument[M]) -> ParsedDocument[M] | None:
        """Return a document with this update applied, or None when nothing changed."""
        updates = _summary_tag_updates(
            document, summary=self.summary, tags=self.tags, fields_set=self.model_fields_set
        )
        metadata = document.metadata
        if (
            "status" in self.model_fields_set
            and _has_status(metadata)
            and metadata.status != self.status
        ):
            updates["status"] = self.status
        return _apply_updates(updates, document)


# --- Queries ---------------------------------------------------------------

# The widest set of stored sort keys; plans widen this with `last_activity_at`.
type DocumentSort = Literal["name", "created_at", "modified_at"]
type PlanSort = Literal["name", "created_at", "modified_at", "last_activity_at"]

DOCUMENT_SORTS: tuple[DocumentSort, ...] = ("name", "created_at", "modified_at")
PLAN_SORTS: tuple[PlanSort, ...] = ("name", "created_at", "modified_at", "last_activity_at")


class DocumentQuery(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    tags: set[Tag] | None = None
    # Widened to every sort key a subclass may accept; the validator narrows it to
    # the keys this document kind stores.
    sort: PlanSort = "name"
    descending: bool = False
    limit: PositiveInt | None = None

    @field_validator("sort")
    @classmethod
    def _validate_sort(cls, value: PlanSort) -> PlanSort:
        if value not in DOCUMENT_SORTS:
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
        if not _has_status(metadata):
            return False
        return metadata.status in self.statuses


class PlanQuery(StatusQuery[PlanStatus]):
    """Plan listing filters; plans are the one kind that can sort by activity."""

    @override
    @field_validator("sort")
    @classmethod
    def _validate_sort(cls, value: PlanSort) -> PlanSort:
        if value not in PLAN_SORTS:
            raise ValueError("Sort key is not supported for this document kind")
        return value


class TaskQuery(StatusQuery[TaskStatus]):
    pass


# --- Search ----------------------------------------------------------------

DEFAULT_GLOB = "**/*.md"


class SearchQuery(BaseModel):
    """Criteria for a filesystem-level search under the project store.

    ``query`` is a tantivy query string: terms, ``"phrases"``, ``field:term``, ``+``/``-``,
    ``AND``/``OR``, ``^boost``, ranges and set terms. Fuzzy (one-typo, prefix) matching is
    on by default; ``is_exact`` turns it off. Regex terms need ``allow_regex`` and a field
    prefix.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    query: str | None = None
    globs: list[str] = Field(default_factory=list)
    plan: Name | None = None
    limit: PositiveInt | None = None
    allow_regex: bool = False
    is_exact: bool = False

    @field_validator("globs")
    @classmethod
    def _validate_globs(cls, globs: list[str]) -> list[str]:
        """Reject absolute or parent-relative globs at the edge; keep the pattern text."""
        for glob in globs:
            validate_relative_path(glob)
        return globs


class SearchMatch(DocumentIdentity):
    """A matched file with its store-relative path and plan/task/context membership.

    ``score`` is the tantivy BM25 relevance; it is only set for query searches and is
    meaningful relative to the other entries of the same query, not as an absolute score.
    """

    path: RelativePath
    score: float | None = None


# --- Batch results ---------------------------------------------------------


class CreateFailure(BaseModel):
    """A name from a batch creation that was not created, with the machine reason."""

    name: str
    reason: Literal["invalid_name", "exists", "failed"]
    message: str


class BatchCreated[T](BaseModel):
    """The outcome of a batch creation: created documents and per-name failures."""

    created: list[T]
    failures: list[CreateFailure]


class SearchSkip(BaseModel):
    """A file the search could not read, with why, reported instead of logged."""

    path: RelativePath
    reason: str


# --- Overviews -------------------------------------------------------------


class PlanOverview(BaseModel):
    """Plan-level overview for `machi plan info [-p NAME]`."""

    is_current: bool
    plan: PlanRecord
    tasks_by_status: dict[TaskStatus, int]
    context_count: int


class ProjectOverview(BaseModel):
    """Project-wide aggregates for `machi info`."""

    current_plan: Name | None
    # None when no plan is selected; otherwise whether the selection still exists.
    current_plan_exists: bool | None
    plan_count: int
    plans_by_status: dict[PlanStatus, int]
    tasks_by_status: dict[TaskStatus, int]
    context_count: int
    doc_count: int
    recent_plans: list[PlanRecord]
