"""Agent-mode targeting: environment detection and plan policy (D1)."""

from pathlib import Path

import pytest
from harness import AGENT_DEPENDENCIES as AGENT
from harness import cli, read_state, seed

from machinate.cli.models import ShowResult
from machinate.cli.project_setup import prepare_project
from machinate.cli.settings import Settings

PLAN_COMMANDS: list[list[str]] = [
    ["plan", "show"],
    ["plan", "info"],
    ["plan", "path"],
    ["plan", "update", "--status", "active"],
    ["task", "list"],
    ["context", "list"],
]


def test_unset_environment_is_human_mode() -> None:
    settings = Settings.from_environ({})
    assert settings.is_agent_mode is False
    assert settings.ai_agent is None
    assert settings.format == "text"


def test_machi_ai_agent_enables_agent_mode() -> None:
    settings = Settings.from_environ({"MACHI_AI_AGENT": "claude-code"})
    assert settings.is_agent_mode is True
    assert settings.ai_agent == "claude-code"
    assert settings.format == "json"


def test_ai_agent_alias_enables_agent_mode() -> None:
    settings = Settings.from_environ({"AI_AGENT": "cursor"})
    assert settings.is_agent_mode is True
    assert settings.ai_agent == "cursor"


def test_machi_ai_agent_wins_alias() -> None:
    settings = Settings.from_environ({"MACHI_AI_AGENT": "machi-name", "AI_AGENT": "other"})
    assert settings.ai_agent == "machi-name"


def test_empty_variable_means_human_mode() -> None:
    assert Settings.from_environ({"MACHI_AI_AGENT": ""}).is_agent_mode is False
    assert Settings.from_environ({"AI_AGENT": ""}).is_agent_mode is False


def test_empty_machi_ai_agent_forces_human_mode() -> None:
    settings = Settings.from_environ({"MACHI_AI_AGENT": "", "AI_AGENT": "cursor"})
    assert settings.is_agent_mode is False
    assert settings.format == "text"


def test_explicit_format_beats_agent_default() -> None:
    settings = Settings.from_environ({"MACHI_AI_AGENT": "claude-code", "MACHI_FORMAT": "text"})
    assert settings.format == "text"


@pytest.mark.parametrize("arguments", PLAN_COMMANDS)
def test_agent_mode_requires_explicit_plan(project: Path, arguments: list[str]) -> None:
    """A current plan is set, but agent mode still refuses to use it without -p."""
    seed.plan(project, "auth")
    prepare_project(project).plans.set_current("auth")
    error = cli.error([*arguments, "-P", str(project)], dependencies=AGENT)
    assert error.command == " ".join(arguments[:2])


def test_agent_mode_allows_explicit_plan(project: Path) -> None:
    seed.plan(project, "auth")
    parsed = cli.json(
        ShowResult,
        ["plan", "show", "-p", "auth", "-P", str(project)],
        dependencies=AGENT,
    )
    assert parsed.plan.name == "auth"


def test_agent_mode_rejects_plan_select(project: Path) -> None:
    seed.plan(project, "auth")
    seed.plan(project, "other")
    prepare_project(project).plans.set_current("other")
    error = cli.error(["plan", "select", "auth", "-P", str(project)], dependencies=AGENT)
    assert error.command == "plan select"
    assert read_state(project).current_plan == "other"


def test_agent_mode_rejects_plan_unselect(project: Path) -> None:
    seed.plan(project, "auth")
    prepare_project(project).plans.set_current("auth")
    error = cli.error(["plan", "unselect", "-P", str(project)], dependencies=AGENT)
    assert error.command == "plan unselect"
    assert read_state(project).current_plan == "auth"
