from __future__ import annotations

from pathlib import Path

from machinate.project_state import get_plan_dir, resolve_current_plan
from machinate.templating import render_context

CONTEXT_DIR = "context"


def add_context(plans_dir: Path, name: str | None = None, filename: str | None = None) -> Path:
    """Ensure context/ exists and return the path.

    If filename is given, creates the file if needed and returns the full file path.
    Otherwise returns the context directory.
    """
    resolved = resolve_current_plan(plans_dir, name)
    plan_dir = get_plan_dir(plans_dir, resolved)
    context_dir = plan_dir / CONTEXT_DIR
    context_dir.mkdir(exist_ok=True)
    if filename:
        if not filename.endswith(".md"):
            filename = f"{filename}.md"
        path = context_dir / filename
        if not path.exists():
            path.write_text(render_context(path.stem))
        return path
    return context_dir


def list_context(plans_dir: Path, name: str | None = None) -> list[Path]:
    """List context file paths for a plan (sorted). Defaults to current plan."""
    resolved = resolve_current_plan(plans_dir, name)
    plan_dir = get_plan_dir(plans_dir, resolved)
    context_dir = plan_dir / CONTEXT_DIR
    if not context_dir.is_dir():
        return []
    return sorted(f for f in context_dir.iterdir() if f.is_file())
