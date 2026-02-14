from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

PlanStatus = Literal["draft", "active", "done"]
TaskStatus = Literal["todo", "in-progress", "done"]


class PlanFrontmatter(BaseModel):
    created: date = Field(default_factory=date.today)
    status: PlanStatus = "draft"


class TaskFrontmatter(BaseModel):
    created: date = Field(default_factory=date.today)
    status: TaskStatus = "todo"


class ContextFrontmatter(BaseModel):
    created: date = Field(default_factory=date.today)


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
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)
