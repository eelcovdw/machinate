"""Agent-mode targeting: environment detection and plan policy."""

from pathlib import Path

import pytest
from harness import AGENT_DEPENDENCIES as AGENT
from harness import cli, read_state, seed_plan

from machinate.cli.models import PlanShowResult
from machinate.cli.project_setup import open_project
from machinate.cli.settings import Settings

PLAN_COMMANDS: list[list[str]] = [
    ["plan", "show"],
    ["task", "list"],
    ["context", "list"],
]


@pytest.mark.parametrize(
    ("environment", "is_agent_mode", "ai_agent"),
    [
        ({}, False, None),
        ({"MACHI_AI_AGENT": ""}, False, ""),
        ({"AI_AGENT": ""}, False, ""),
        ({"MACHI_AI_AGENT": "claude-code"}, True, "claude-code"),
        ({"AI_AGENT": "cursor"}, True, "cursor"),
        ({"MACHI_AI_AGENT": "machi-name", "AI_AGENT": "other"}, True, "machi-name"),
        ({"MACHI_AI_AGENT": "", "AI_AGENT": "cursor"}, False, ""),
    ],
)
def test_agent_mode_detection(
    environment: dict[str, str], is_agent_mode: bool, ai_agent: str | None
) -> None:
    settings = Settings.from_environ(environment)
    assert settings.is_agent_mode is is_agent_mode
    assert settings.ai_agent == ai_agent
    assert settings.output_format == ("json" if is_agent_mode else "text")


def test_explicit_format_beats_agent_default() -> None:
    settings = Settings.from_environ({"MACHI_AI_AGENT": "claude-code", "MACHI_FORMAT": "text"})
    assert settings.format == "text"


@pytest.mark.parametrize("arguments", PLAN_COMMANDS)
def test_agent_mode_requires_explicit_plan(project: Path, arguments: list[str]) -> None:
    """A current plan is set, but agent mode still refuses to use it without -p."""
    seed_plan(project, "auth")
    open_project(project).plans.select_plan("auth")
    error = cli.error([*arguments, "-P", str(project)], code="input", dependencies=AGENT)
    assert error.command == " ".join(arguments[:2])


def test_agent_mode_allows_explicit_plan(project: Path) -> None:
    seed_plan(project, "auth")
    parsed = cli.json(
        PlanShowResult,
        ["plan", "show", "auth", "-P", str(project)],
        dependencies=AGENT,
    )
    assert parsed.plan.name == "auth"


def test_agent_mode_rejects_plan_writes_without_changing_selection(project: Path) -> None:
    seed_plan(project, "auth")
    seed_plan(project, "other")
    open_project(project).plans.select_plan("other")
    select = cli.error(
        ["plan", "select", "auth", "-P", str(project)], code="input", dependencies=AGENT
    )
    assert select.command == "plan select"
    unselect = cli.error(["plan", "unselect", "-P", str(project)], code="input", dependencies=AGENT)
    assert unselect.command == "plan unselect"
    assert read_state(project).current_plan == "other"
