from __future__ import annotations

import shutil
from pathlib import Path

SKILLS_DIR = Path(__file__).parent


def install_skills(project_root: Path) -> None:
    """Install bundled skill templates into the project's .claude/skills/ directory."""
    target = project_root / ".claude" / "skills"
    target.mkdir(parents=True, exist_ok=True)

    for skill_dir in SKILLS_DIR.iterdir():
        if not skill_dir.is_dir() or skill_dir.name.startswith("__"):
            continue
        dest = target / skill_dir.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
