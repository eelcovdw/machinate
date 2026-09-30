from pathlib import Path

import pytest
from harness import AGENT_DEPENDENCIES as AGENT
from harness import cli

from machinate.cli.models import InstructionsResult


def test_instructions_json() -> None:
    payload = cli.json(InstructionsResult, ["instructions", "--format", "json"])
    assert payload.command == "instructions"


def test_instructions_writes_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = cli.run(["instructions"])
    assert result.exit_code == 0
    assert list(tmp_path.iterdir()) == []


def test_instructions_invalid_format() -> None:
    result = cli.run(["instructions", "--format", "yaml"])
    assert result.exit_code == 2


def test_instructions_json_default_in_agent_mode() -> None:
    payload = cli.json(
        InstructionsResult,
        ["instructions"],
        dependencies=AGENT,
    )
    assert payload.command == "instructions"


def test_agents_md_machinate_section_matches_instructions() -> None:
    payload = cli.json(InstructionsResult, ["instructions", "--format", "json"])
    agents = (Path(__file__).resolve().parents[2] / "AGENTS.md").read_text()
    section = agents[agents.index("## Machinate") :]
    assert section.strip() == payload.text.strip()
