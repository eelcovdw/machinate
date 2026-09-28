from pathlib import Path

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app
from machinate.cli.models import ErrorResult, InstructionsResult

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


def test_instructions_json() -> None:
    result = runner.invoke(app, ["instructions", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = InstructionsResult.model_validate_json(result.stdout)
    assert payload.command == "instructions"


def test_instructions_writes_no_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["instructions"])
    assert result.exit_code == 0, result.output
    assert list(tmp_path.iterdir()) == []


def test_instructions_invalid_format() -> None:
    result = runner.invoke(app, ["instructions", "--format", "yaml"])
    assert result.exit_code == 1
    assert "format" in ErrorResult.model_validate_json(result.stderr).error


def test_instructions_json_default_in_automation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, ["instructions"])
    assert result.exit_code == 0, result.output
    assert InstructionsResult.model_validate_json(result.stdout).command == "instructions"
