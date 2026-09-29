from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

from machinate.storage.models import Name, RelativePath, validate_relative_path
from machinate.storage.queries import DocumentKind

DEFAULT_GLOB = "**/*.md"


class FindQuery(BaseModel):
    """Criteria for a filesystem-level search under the project store.

    ``query`` is a tantivy query string: terms, ``"phrases"``, ``field:term``, ``+``/``-``,
    ``AND``/``OR``, ``^boost``, ranges and set terms. Fuzzy (one-typo, prefix) matching is
    on by default; ``exact`` turns it off. Regex terms need ``regex`` and a field prefix.

    Future entity filters are intentionally absent from this version; they slot in here
    without changing the service or CLI contract: ``kinds``, ``tags``, ``statuses``,
    ``created_range``, ``updated_range``.
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


class FindEntry(BaseModel):
    """A matched file with its storage-relative path and plan/task/context membership.

    ``score`` is the tantivy BM25 relevance; it is only set for query searches and is
    meaningful relative to the other entries of the same query, not as an absolute score.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    path: RelativePath
    kind: DocumentKind
    plan: str | None = None
    name: str | None = None
    score: float | None = None
