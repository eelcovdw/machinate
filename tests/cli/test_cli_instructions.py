from pathlib import Path

import pytest
from harness import AUTOMATION_DEPENDENCIES as AUTOMATION
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
    error = cli.error(["instructions", "--format", "yaml"])
    assert error.command == "instructions"


def test_instructions_json_default_in_automation() -> None:
    payload = cli.json(
        InstructionsResult,
        ["instructions"],
        dependencies=AUTOMATION,
    )
    assert payload.command == "instructions"
