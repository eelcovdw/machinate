from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Self

import tomli_w
from pydantic import BaseModel

STATE_FILE = "machinate.toml"


class ProjectState(BaseModel):
    current_plan: str | None = None

    @classmethod
    def load(cls, path: Path) -> Self:
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            return cls.model_validate(tomllib.load(f))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            tomli_w.dump(self.model_dump(exclude_none=True), f)


def resolve_current_plan(plans_dir: Path, name: str | None = None) -> str:
    """Resolve plan name: explicit arg or current plan from state."""
    if name is not None:
        return name
    state = ProjectState.load(plans_dir / STATE_FILE)
    if state.current_plan is None:
        msg = "No current plan. Pass a name or run 'machi set' first."
        raise ValueError(msg)
    return state.current_plan


def get_plan_dir(plans_dir: Path, name: str) -> Path:
    """Get and validate a plan directory exists."""
    plan_dir = plans_dir / name
    if not plan_dir.is_dir():
        msg = f"Plan '{name}' not found."
        raise FileNotFoundError(msg)
    return plan_dir
