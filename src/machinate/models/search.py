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
    snippets: bool = True
    context: int = Field(default=0, ge=0)
    snippet_chars: PositiveInt = 160


class FindSnippet(BaseModel):
    """A matched window of a document, with 1-based inclusive line numbers.

    ``text`` is the raw file text for lines ``line``..``line_end`` (widened by the query's
    context); ``highlights`` are character offsets into ``text`` for the matched terms.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    line: PositiveInt
    line_end: PositiveInt
    text: str
    highlights: list[tuple[int, int]] = Field(default_factory=list)


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
    snippets: list[FindSnippet] = Field(default_factory=list)
