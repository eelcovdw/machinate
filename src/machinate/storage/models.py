from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, ClassVar, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
)

from .summary import derive_summary


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
    """Drop a trailing ``.md``; names map to ``{name}.md`` files."""
    return value[: -len(".md")] if value.lower().endswith(".md") else value


Name = Annotated[str, BeforeValidator(normalize_name), AfterValidator(validate_name)]


def validate_collection_name(value: str) -> str:
    for component in value.split("/"):
        validate_name(component)
    return value


TaskName = Annotated[str, BeforeValidator(normalize_name), AfterValidator(validate_collection_name)]
ContextName = Annotated[
    str, BeforeValidator(normalize_name), AfterValidator(validate_collection_name)
]
DocName = Annotated[str, BeforeValidator(normalize_name), AfterValidator(validate_collection_name)]


class TaskNameInput(BaseModel):
    name: TaskName


class ContextNameInput(BaseModel):
    name: ContextName


class DocNameInput(BaseModel):
    name: DocName


class NameInput(BaseModel):
    name: Name


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


class PathInput(BaseModel):
    path: RelativePath


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
    # (see Document.get_or_derive_summary).
    summary: str | None = None
    tags: list[Tag] = Field(default_factory=list)

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


class Document[M: Metadata](BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True)

    metadata: M
    body: str

    def get_or_derive_summary(self) -> str | None:
        """Return the authored summary, or one derived from the body."""
        if self.metadata.summary is not None:
            return self.metadata.summary
        return derive_summary(self.body)


class FileMetadata(BaseModel):
    path: RelativePath
    modified: datetime
    kind: Literal["file", "directory"]


class ProjectState(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True)

    project_name: Name
    current_plan: Name | None = None
