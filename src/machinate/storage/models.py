"""Storage-internal models: file stats, the project state file, and collections."""

from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from machinate.models.documents import Name, RelativePath


class FileMetadata(BaseModel):
    path: RelativePath
    modified_at: datetime
    kind: Literal["file", "directory"]


class ProjectState(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True, extra="forbid")

    project_name: Name
    current_plan: Name | None = None


class DocumentScope(BaseModel):
    path: RelativePath
    pattern: RelativePath


class DocumentCollection(DocumentScope):
    # Plans use their parent name; other documents keep collection-relative directories.
    name_source: Literal["parent", "stem"] = "stem"
    activity_scopes: tuple[DocumentScope, ...] = ()
