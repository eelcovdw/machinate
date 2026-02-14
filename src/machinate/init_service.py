from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from machinate.project_state import STATE_FILE, ProjectState
from machinate.settings import Settings
from machinate.templating.templates import render_project

DEFAULT_BASE_PLANS_DIR: Path = Path.home() / ".machinate"


def plan_file(name: str) -> str:
    """Return the plan filename for a given plan name."""
    return f"plan-{name}.md"


ALLOW_RULES = [
    "Bash(machi list)",
    "Bash(machi show)",
    "Bash(machi show *)",
    "Bash(machi task list)",
    "Bash(machi context list)",
    "Read(.claude/plans/**)",
]


@dataclass
class InitResult:
    plans_dir: Path
    project_root: Path
    project_name: str
    symlink: Path | None = None


def find_project_root(start: Path | None = None) -> Path:
    """Walk up from start (default: cwd) looking for .git."""
    start = start or Path.cwd()
    for parent in [start, *start.parents]:
        if (parent / ".git").exists():
            return parent
    return start


def resolve_project_root(project_root: Path | None = None) -> Path:
    """Resolve project_root: explicit arg > git root > cwd."""
    if project_root is not None:
        return project_root
    return find_project_root()


def claude_plans_dir(project_root: Path) -> Path:
    return project_root / ".claude" / "plans"


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

    return claude_plans_dir(project_root)


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
    resolved_root = resolve_project_root(project_root)
    resolved_name = project_name or _resolve_project_name(resolved_root, settings)
    resolved_plans = _resolve_plans_dir(
        resolved_root,
        settings,
        plans_dir=plans_dir,
        base_plans_dir=base_plans_dir,
        project_name=resolved_name,
    )

    resolved_plans = resolved_plans.expanduser().resolve()
    cp = claude_plans_dir(resolved_root).expanduser()
    # Don't resolve() claude_plans — if it's already a symlink to resolved_plans,
    # resolve() would follow it and make both equal, hiding the symlink.
    cp = cp.parent.resolve() / cp.name

    symlink = cp if resolved_plans != cp else None
    return InitResult(
        plans_dir=resolved_plans,
        project_root=resolved_root,
        project_name=resolved_name,
        symlink=symlink,
    )


def update_claude_settings(project_root: Path) -> None:
    """Merge machinate allow rules into .claude/settings.json."""
    settings_path = project_root / ".claude" / "settings.json"
    data: dict[str, object] = (
        json.loads(settings_path.read_text()) if settings_path.exists() else {}
    )

    perms_raw = data.get("permissions")
    perms: dict[str, object] = dict(perms_raw) if isinstance(perms_raw, dict) else {}  # pyright: ignore[reportUnknownArgumentType]
    allow_raw = perms.get("allow")
    existing: list[object] = list(allow_raw) if isinstance(allow_raw, list) else []  # pyright: ignore[reportUnknownArgumentType]

    merged = list(existing)
    for rule in ALLOW_RULES:
        if rule not in merged:
            merged.append(rule)

    perms["allow"] = merged
    data["permissions"] = perms
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2) + "\n")


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
    if not state_file.exists():
        ProjectState(project_name=plan.project_name).save(state_file)
    elif override:
        existing_state = ProjectState.load(state_file)
        existing_state.project_name = plan.project_name
        existing_state.save(state_file)

    project_file = plan.plans_dir / f"project-{plan.project_name}.md"
    if not project_file.exists():
        project_file.write_text(render_project(plan.project_name))


def migrate_plan_files(plans_dir: Path) -> None:
    """Rename old plan.md files to plan-{name}.md."""
    for d in plans_dir.iterdir():
        if not d.is_dir():
            continue
        old = d / "plan.md"
        new = d / plan_file(d.name)
        if old.exists() and not new.exists():
            old.rename(new)
