"""Domain document models: names and paths, frontmatter metadata, summary
derivation, the generic parsed/listed-document shapes, and the per-resource
entity classes.

Models are ordered top-down by dependency: primitives, metadata, summary,
document shapes, then entities.
"""

# --- Names and paths -------------------------------------------------------

import re
import unicodedata
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, ClassVar, Final, Literal, Self, cast

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
)


def validate_name(value: str) -> str:
    if (
        not value.strip()
        or value != value.strip()
        or value in {".", ".."}
        or any(char in value for char in "/\\:")
        or any(not char.isprintable() for char in value)
    ):
        raise ValueError("Expected a nonempty name without path separators or control characters")
    return value


def normalize_name(value: str) -> str:
    """Unicode-normalize to NFC and drop a trailing ``.md``; names map to ``{name}.md`` files."""
    name = unicodedata.normalize("NFC", value)
    return name[: -len(".md")] if name.lower().endswith(".md") else name


Name = Annotated[str, BeforeValidator(normalize_name), AfterValidator(validate_name)]


def validate_nested_name(value: str) -> str:
    for component in value.split("/"):
        validate_name(component)
    return value


NestedName = Annotated[str, BeforeValidator(normalize_name), AfterValidator(validate_nested_name)]

NAME_ADAPTER: TypeAdapter[Name] = TypeAdapter(Name)
NESTED_NAME_ADAPTER: TypeAdapter[NestedName] = TypeAdapter(NestedName)


def validate_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, (str, PurePosixPath)):
        raise ValueError("Expected a relative POSIX path")  # noqa: TRY004 - Pydantic validation
    raw = str(value)
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or ".." in path.parts
        or PureWindowsPath(raw).drive
        or "\\" in raw
        or any(not char.isprintable() for char in raw)
    ):
        raise ValueError("Expected a relative path without '..', a drive, or control characters")
    return path


RelativePath = Annotated[PurePosixPath, BeforeValidator(validate_relative_path)]
RELATIVE_PATH_ADAPTER: TypeAdapter[RelativePath] = TypeAdapter(RelativePath)


# --- Frontmatter metadata --------------------------------------------------


def validate_tag(value: str) -> str:
    tag = value.strip()
    if not tag or any(not char.isprintable() for char in tag):
        raise ValueError("Expected a nonempty tag without control characters")
    return tag


Tag = Annotated[str, AfterValidator(validate_tag)]


class Metadata(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", validate_assignment=True)

    created: AwareDatetime
    # Optional authored summary; readers fall back to a derived one
    # (see ParsedDocument.get_or_derive_summary).
    summary: str | None = None
    tags: list[Tag] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def _coerce_tags(cls, value: object) -> object:
        """Accept a scalar tags value or non-string items, as hand-edited YAML produces."""
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            return [
                item if isinstance(item, str) else str(item) for item in cast("list[object]", value)
            ]
        return value

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: object) -> object:
        """Accept a non-string summary scalar (e.g. a YAML number) as text."""
        return value if value is None or isinstance(value, str) else str(value)

    @field_validator("tags", mode="after")
    @classmethod
    def _dedupe_tags(cls, tags: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for tag in tags:
            key = tag.casefold()
            if key not in seen:
                seen.add(key)
                deduped.append(tag)
        return deduped


type PlanStatus = Literal["draft", "active", "done"]
type TaskStatus = Literal["todo", "in-progress", "done"]


class StatusMetadata[S: str](Metadata):
    status: S


class PlanMetadata(StatusMetadata[PlanStatus]):
    status: PlanStatus = "draft"


class TaskMetadata(StatusMetadata[TaskStatus]):
    status: TaskStatus = "todo"


class ContextMetadata(Metadata):
    pass


class DocMetadata(Metadata):
    pass


# --- Summary derivation ----------------------------------------------------

_HEADING: Final = re.compile(r"^#{1,6}(\s|$)")
_LABEL: Final = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,30}:(\s|$)")
_FENCE: Final = re.compile(r"^\s*(```|~~~)")
_LINK: Final = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def derive_summary(body: str) -> str | None:
    """Return the first prose paragraph of ``body`` as a single line.

    Fenced code blocks are excluded, and only the leading run of markdown
    headings and single-line ``Label:`` preambles (such as ``Project: machinate``)
    is skipped, so a plan body that opens with a title heading does not summarise
    as that heading while a later ``Label:`` line stays prose. Inline emphasis,
    code ticks, and links are stripped. Returns ``None`` when the body has no prose.
    """
    paragraphs = _paragraphs(_without_fences(body))
    first_label_paragraph: list[str] | None = None
    for paragraph in paragraphs:
        remaining = _strip_leading(paragraph)
        if remaining:
            return _clean(" ".join(remaining))
        if first_label_paragraph is None and any(_LABEL.match(line.strip()) for line in paragraph):
            first_label_paragraph = paragraph
    if first_label_paragraph is not None:
        # The whole body is a single label preamble (e.g. a lone ``TODO: ...``).
        labels = [line.strip() for line in first_label_paragraph if _LABEL.match(line.strip())]
        return _clean(" ".join(labels))
    return None


def _strip_leading(lines: list[str]) -> list[str]:
    """Drop leading heading/label lines, keeping everything from the first prose line."""
    remaining: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not remaining and (_HEADING.match(stripped) or _LABEL.match(stripped)):
            continue
        remaining.append(line)
    return remaining


def _clean(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    return text.replace("**", "").replace("__", "").replace("`", "")


def _without_fences(body: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return "\n".join(lines)


def _paragraphs(body: str) -> list[list[str]]:
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in body.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            paragraphs.append(current)
            current = []
    if current:
        paragraphs.append(current)
    return paragraphs


# --- Document shapes -------------------------------------------------------


class ParsedDocument[M: Metadata](BaseModel):
    """A parsed document: validated frontmatter metadata plus its body."""

    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True)

    metadata: M
    body: str

    def get_or_derive_summary(self) -> str | None:
        """Return the authored summary, or one derived from the body."""
        if self.metadata.summary is not None:
            return self.metadata.summary
        return derive_summary(self.body)


type DocumentKind = Literal["plan", "task", "context", "doc", "unknown"]


class DocumentMembership(BaseModel):
    """Kind and owning plan/name for a storage-relative path."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: DocumentKind
    plan: Name | None = None
    name: NestedName | None = None


class DocumentRecord[M: Metadata](BaseModel):
    """A listed document: membership-shape record with metadata and effective summary."""

    name: NestedName
    path: RelativePath
    metadata: M
    last_activity_at: datetime
    # Effective summary: the authored one, otherwise derived from the body.
    summary: str | None = None

    @classmethod
    def from_document(
        cls,
        document: ParsedDocument[M],
        *,
        name: NestedName,
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


# --- Per-resource entities -------------------------------------------------


class Plan(BaseModel):
    name: Name
    path: RelativePath
    document: ParsedDocument[PlanMetadata]
    modified_at: datetime


class Task(BaseModel):
    name: NestedName
    path: RelativePath
    document: ParsedDocument[TaskMetadata]
    modified_at: datetime


class Context(BaseModel):
    name: NestedName
    path: RelativePath
    document: ParsedDocument[ContextMetadata]
    modified_at: datetime


class Doc(BaseModel):
    name: NestedName
    path: RelativePath
    document: ParsedDocument[DocMetadata]
    modified_at: datetime
