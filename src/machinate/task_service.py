from __future__ import annotations

from pathlib import Path

from machinate.project_state import get_plan_dir, resolve_current_plan
from machinate.templating import render_task

TASKS_DIR = "tasks"


def add_task(plans_dir: Path, name: str | None = None, filename: str | None = None) -> Path:
    """Ensure tasks/ exists and return the path.

    If filename is given, creates the file if needed and returns the full file path.
    Otherwise returns the tasks directory.
    """
    resolved = resolve_current_plan(plans_dir, name)
    plan_dir = get_plan_dir(plans_dir, resolved)
    tasks_dir = plan_dir / TASKS_DIR
    tasks_dir.mkdir(exist_ok=True)
    if filename:
        if not filename.endswith(".md"):
            filename = f"{filename}.md"
        path = tasks_dir / filename
        if not path.exists():
            path.write_text(render_task(path.stem))
        return path
    return tasks_dir


def list_tasks(plans_dir: Path, name: str | None = None) -> list[Path]:
    """List task file paths for a plan (sorted). Defaults to current plan."""
    resolved = resolve_current_plan(plans_dir, name)
    plan_dir = get_plan_dir(plans_dir, resolved)
    tasks_dir = plan_dir / TASKS_DIR
    if not tasks_dir.is_dir():
        return []
    return sorted(f for f in tasks_dir.iterdir() if f.is_file())
