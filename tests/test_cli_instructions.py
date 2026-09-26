from pathlib import Path
from typing import override

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, create_cli
from machinate.cli.commands.catalog import COMMANDS
from machinate.cli.dependencies import Dependencies
from machinate.cli.formatting import Formatter
from machinate.cli.models import CommandResult, ErrorResult, InstructionsResult

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_INTERACTIVE", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_instructions_text() -> None:
    result = runner.invoke(app, ["instructions"])
    assert result.exit_code == 0, result.output
    assert "## Machinate" in result.stdout
    assert "machi plan" in result.stdout
    assert "-p NAME" in result.stdout
    assert "MACHI_INTERACTIVE=false" in result.stdout
    assert "machi schema" in result.stdout
    assert "machi plan path" in result.stdout


def test_instructions_json() -> None:
    result = runner.invoke(app, ["instructions", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = InstructionsResult.model_validate_json(result.stdout)
    assert payload.command == "instructions"
    assert "## Machinate" in payload.text


def test_instructions_lists_every_registered_command() -> None:
    result = runner.invoke(app, ["instructions"])
    for spec in COMMANDS:
        assert f"machi {spec.name}" in result.stdout


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
    monkeypatch.setenv("MACHI_INTERACTIVE", "false")
    result = runner.invoke(app, ["instructions"])
    assert result.exit_code == 0, result.output
    assert InstructionsResult.model_validate_json(result.stdout).command == "instructions"


def test_instructions_formatter_injection() -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["instructions", "--format", "custom"])
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], InstructionsResult)


def test_instructions_help() -> None:
    result = runner.invoke(app, ["instructions", "--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout


def test_instructions_parser_errors_use_json() -> None:
    result = runner.invoke(app, ["instructions", "--unknown"], env={"MACHI_INTERACTIVE": "false"})
    assert result.exit_code == 2
    assert ErrorResult.model_validate_json(result.stderr).command == "instructions"
