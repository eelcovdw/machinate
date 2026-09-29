"""Shared fixtures for the Machinate test suite.

Tests do not depend on the environment: every CLI invocation injects an explicit
``Settings`` through ``Dependencies`` (see ``harness.py``), and every ``MACHI_*`` /
``AI_AGENT`` variable is removed before each test as a safety net. Only the
settings-loading tests read environment variables directly, via ``monkeypatch``.
"""

import os
from pathlib import Path

import pytest

from machinate.storage import ProjectState, ProjectStateStore


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every variable that could flip settings or agent mode."""
    for name in list(os.environ):
        if name == "AI_AGENT" or name.startswith("MACHI_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """An initialized project with no plans and no current selection."""
    root = tmp_path / "project"
    ProjectStateStore(root / ".machi/machinate.toml").write(ProjectState(project_name="example"))
    return root
