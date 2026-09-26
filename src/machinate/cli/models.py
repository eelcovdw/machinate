from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from machinate.models.plan import PlanSummary


class ProjectScope(BaseModel):
    name: str
    directory: Path
    storage: Path


class ListResult(BaseModel):
    command: Literal["list"] = "list"
    project: ProjectScope
    plans: list[PlanSummary]


class ErrorResult(BaseModel):
    command: Literal["list"] = "list"
    error: str
    project: ProjectScope | None = None


type CommandResult = ListResult | ErrorResult
