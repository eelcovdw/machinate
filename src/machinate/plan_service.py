from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from machinate.context_service import list_context
from machinate.init_service import (
    claude_plans_dir,
    migrate_plan_files,
    plan_file,
    resolve_project_root,
)
from machinate.project_state import (
    STATE_FILE,
    ProjectState,
    get_plan_dir,
    resolve_current_plan,
)
from machinate.task_service import list_tasks
from machinate.templating import PlanStatus, render_plan, update_frontmatter_field

__all__ = ["plan_file"]


def get_plans_dir(project_root: Path | None = None) -> Path:
    """Get the plans directory for an initialized project."""
    root = resolve_project_root(project_root)
    plans = claude_plans_dir(root)
    if not plans.exists():
        msg = f"Not initialized. Run 'machi init' first. (looked in {plans})"
        raise FileNotFoundError(msg)
    migrate_plan_files(plans)
    return plans


def create_plan(plans_dir: Path, name: str, *, exist_ok: bool = False) -> Path:
    """Create a new plan folder with an empty plan.md. Returns the plan directory."""
    plan_dir = plans_dir / name
    if plan_dir.exists():
        if exist_ok:
            return plan_dir
        msg = f"Plan '{name}' already exists."
        raise FileExistsError(msg)
    plan_dir.mkdir(parents=True)
    (plan_dir / plan_file(name)).write_text(render_plan(name))
    return plan_dir


@dataclass
class PlanInfo:
    name: str
    plan_dir: Path
    plan_content: str
    task_files: list[Path]
    context_files: list[Path]


def get_current_plan(plans_dir: Path) -> str | None:
    """Get the current plan name, or None."""
    return ProjectState.load(plans_dir / STATE_FILE).current_plan


def get_project_name(plans_dir: Path) -> str | None:
    """Get the project name from state, or None."""
    return ProjectState.load(plans_dir / STATE_FILE).project_name


def get_project_file(plans_dir: Path) -> Path:
    """Get the path to the project file. Raises if project_name is not set."""
    name = get_project_name(plans_dir)
    if name is None:
        msg = "No project name set. Re-run 'machi init' to set it."
        raise ValueError(msg)
    return plans_dir / f"project-{name}.md"


def set_plan(plans_dir: Path, name: str) -> None:
    """Set the current plan. Validates the plan exists."""
    get_plan_dir(plans_dir, name)
    state = ProjectState.load(plans_dir / STATE_FILE)
    state.current_plan = name
    state.save(plans_dir / STATE_FILE)


def set_plan_status(plans_dir: Path, name: str, status: PlanStatus) -> Path:
    """Update the status in a plan's frontmatter. Returns the plan.md path."""
    plan_dir = get_plan_dir(plans_dir, name)
    path = plan_dir / plan_file(name)
    update_frontmatter_field(path, "status", status)
    return path


def show_plan(plans_dir: Path, name: str | None = None) -> PlanInfo:
    """Get info about a plan. Defaults to current plan."""
    name = resolve_current_plan(plans_dir, name)
    plan_dir = get_plan_dir(plans_dir, name)
    plan_path = plan_dir / plan_file(name)
    plan_content = plan_path.read_text() if plan_path.exists() else ""

    return PlanInfo(
        name=name,
        plan_dir=plan_dir,
        plan_content=plan_content,
        task_files=list_tasks(plans_dir, name),
        context_files=list_context(plans_dir, name),
    )


def list_plans(plans_dir: Path) -> list[str]:
    """List all plan names (sorted)."""
    return sorted(
        d.name for d in plans_dir.iterdir() if d.is_dir() and (d / plan_file(d.name)).exists()
    )
