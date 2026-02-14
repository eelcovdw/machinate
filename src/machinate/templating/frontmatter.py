from __future__ import annotations

from datetime import date
from typing import Literal, get_args

from pydantic import BaseModel, Field

PlanStatus = Literal["draft", "active", "done"]
TaskStatus = Literal["todo", "in-progress", "done"]
PLAN_STATUS_ORDER: tuple[str, ...] = get_args(PlanStatus)
TASK_STATUS_ORDER: tuple[str, ...] = get_args(TaskStatus)


class PlanFrontmatter(BaseModel):
    created: date = Field(default_factory=date.today)
    status: PlanStatus = "draft"
    summary: str = ""


class TaskFrontmatter(BaseModel):
    created: date = Field(default_factory=date.today)
    status: TaskStatus = "todo"
    summary: str = ""


class ContextFrontmatter(BaseModel):
    created: date = Field(default_factory=date.today)
    summary: str = ""


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split markdown into (frontmatter dict, body). Returns empty dict if no frontmatter."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            data[key.strip()] = value.strip()
    return data, body


def render_frontmatter(model: BaseModel) -> str:
    """Render a pydantic model as YAML frontmatter string."""
    lines = ["---"]
    for key, value in model.model_dump().items():  # pyright: ignore[reportAny]
        if isinstance(value, str) and value == "":
            continue
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)
