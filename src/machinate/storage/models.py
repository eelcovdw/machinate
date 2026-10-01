"""Storage-internal models: file stats, the project state file, and collections."""

from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from machinate.models.documents import Name, RelativePath


class FileStat(BaseModel):
    path: RelativePath
    modified_at: datetime


class ProjectState(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(validate_assignment=True, extra="forbid")

    project_name: Name
    current_plan: Name | None = None


class ProjectRedirect(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    project_dir: Path


type ProjectEntry = ProjectState | ProjectRedirect


class DocumentCollection(BaseModel):
    path: RelativePath
    pattern: RelativePath
    # Plans use their parent name; other documents keep collection-relative directories.
    name_source: Literal["parent", "stem"] = "stem"
