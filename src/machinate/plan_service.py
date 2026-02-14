from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from machinate.context_service import list_context
from machinate.project_state import (
    STATE_FILE,
    ProjectState,
    get_plan_dir,
    resolve_current_plan,
)
from machinate.settings import Settings
from machinate.task_service import list_tasks
from machinate.templating import render_plan

DEFAULT_BASE_PLANS_DIR: Path = Path.home() / ".machinate"
PLAN_FILE = "plan.md"


@dataclass
class InitResult:
    plans_dir: Path
    symlink: Path | None = None


def _find_project_root(start: Path | None = None) -> Path:
    """Walk up from start (default: cwd) looking for .git."""
    start = start or Path.cwd()
    for parent in [start, *start.parents]:
        if (parent / ".git").exists():
            return parent
    return start


def _resolve_project_root(project_root: Path | None = None) -> Path:
    """Resolve project_root: explicit arg > git root > cwd."""
    if project_root is not None:
        return project_root
    return _find_project_root()


def _resolve_base_plans_dir(settings: Settings) -> Path:
    """Resolve base_plans_dir: MACHINATE_BASE_DIR > MACHINATE_OBSIDIAN_VAULT > ~/.machinate."""
    if settings.base_dir is not None:
        return settings.base_dir
    if settings.obsidian_vault is not None:
        return settings.obsidian_vault.expanduser() / "machinate"
    return DEFAULT_BASE_PLANS_DIR


def _resolve_project_name(project_root: Path, settings: Settings) -> str:
    """Resolve project_name: MACHINATE_PROJECT > project root dir name."""
    if settings.project is not None:
        return settings.project
    return project_root.name


def _claude_plans_dir(project_root: Path) -> Path:
    return project_root / ".claude" / "plans"


def _resolve_plans_dir(
    project_root: Path,
    settings: Settings,
    *,
    plans_dir: Path | None = None,
    base_plans_dir: Path | None = None,
    project_name: str | None = None,
) -> Path:
    """Resolve the plans directory. Three paths:

    1. Explicit plans_dir — use directly.
    2. base_plans_dir / project_name — from args or env.
    3. project_root / .claude / plans — local fallback.
    """
    if plans_dir is not None:
        return plans_dir

    if base_plans_dir is not None or settings.base_dir or settings.obsidian_vault:
        resolved_base = base_plans_dir or _resolve_base_plans_dir(settings)
        name = project_name or _resolve_project_name(project_root, settings)
        return resolved_base / name

    return _claude_plans_dir(project_root)


def plan_init(
    settings: Settings | None = None,
    project_root: Path | None = None,
    plans_dir: Path | None = None,
    base_plans_dir: Path | None = None,
    project_name: str | None = None,
) -> InitResult:
    """Resolve what init will do, without executing.

    Returns an InitResult describing the planned actions.
    """
    settings = settings or Settings()
    resolved_root = _resolve_project_root(project_root)
    resolved_plans = _resolve_plans_dir(
        resolved_root,
        settings,
        plans_dir=plans_dir,
        base_plans_dir=base_plans_dir,
        project_name=project_name,
    )

    resolved_plans = resolved_plans.expanduser().resolve()
    claude_plans = _claude_plans_dir(resolved_root).expanduser().resolve()

    symlink = claude_plans if resolved_plans != claude_plans else None
    return InitResult(plans_dir=resolved_plans, symlink=symlink)


def execute_init(plan: InitResult, *, override: bool = False) -> None:
    """Execute the init plan: create dirs, symlink, write state file."""
    plan.plans_dir.mkdir(parents=True, exist_ok=True)

    if plan.symlink is not None:
        plan.symlink.parent.mkdir(parents=True, exist_ok=True)
        if plan.symlink.is_symlink():
            if override:
                plan.symlink.unlink()
        elif plan.symlink.is_dir():
            shutil.copytree(plan.symlink, plan.plans_dir, dirs_exist_ok=True)
            shutil.rmtree(plan.symlink)
        if not plan.symlink.exists() and not plan.symlink.is_symlink():
            plan.symlink.symlink_to(plan.plans_dir)

    state_file = plan.plans_dir / STATE_FILE
    if not state_file.exists() or override:
        ProjectState().save(state_file)


def get_plans_dir(project_root: Path | None = None) -> Path:
    """Get the plans directory for an initialized project."""
    root = _resolve_project_root(project_root)
    plans = _claude_plans_dir(root)
    if not plans.exists():
        msg = f"Not initialized. Run 'machi init' first. (looked in {plans})"
        raise FileNotFoundError(msg)
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
    (plan_dir / PLAN_FILE).write_text(render_plan(name))
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


def set_plan(plans_dir: Path, name: str) -> None:
    """Set the current plan. Validates the plan exists."""
    get_plan_dir(plans_dir, name)
    state = ProjectState.load(plans_dir / STATE_FILE)
    state.current_plan = name
    state.save(plans_dir / STATE_FILE)


def show_plan(plans_dir: Path, name: str | None = None) -> PlanInfo:
    """Get info about a plan. Defaults to current plan."""
    name = resolve_current_plan(plans_dir, name)
    plan_dir = get_plan_dir(plans_dir, name)
    plan_file = plan_dir / PLAN_FILE
    plan_content = plan_file.read_text() if plan_file.exists() else ""

    return PlanInfo(
        name=name,
        plan_dir=plan_dir,
        plan_content=plan_content,
        task_files=list_tasks(plans_dir, name),
        context_files=list_context(plans_dir, name),
    )


def list_plans(plans_dir: Path) -> list[str]:
    """List all plan names (sorted)."""
    return sorted(d.name for d in plans_dir.iterdir() if d.is_dir() and (d / PLAN_FILE).exists())
