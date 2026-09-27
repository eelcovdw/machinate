from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from machinate.storage.models import Name, RelativePath
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
