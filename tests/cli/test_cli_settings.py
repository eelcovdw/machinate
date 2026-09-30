from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, build_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult, PlanListResult
from machinate.cli.settings import Settings

runner = CliRunner()


@pytest.mark.parametrize(
    ("environment", "ai_agent", "format_name"),
    [
        ({}, None, None),
        ({"ai_agent": "someone", "format": "json"}, None, None),
        ({"MACHI_AI_AGENT": "someone", "MACHI_FORMAT": "json"}, "someone", "json"),
    ],
)
def test_environment_names_are_read_case_sensitively(
    environment: dict[str, str], ai_agent: str | None, format_name: str | None
) -> None:
    settings = Settings.from_environ(environment)
    assert settings.ai_agent == ai_agent
    assert settings.format == format_name


def test_invalid_env_format_reports_field(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "human")
    result = runner.invoke(app, ["plan", "list", "-P", str(project)])
    assert result.exit_code == 1
    assert "MACHI_FORMAT" in ErrorResult.model_validate_json(result.stderr).error


def test_help_does_not_open_project(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = Mock(side_effect=AssertionError("help must not prepare a project"))
    custom = build_cli(Dependencies(open_project=factory))
    monkeypatch.setenv("MACHI_LOG_LEVEL", "invalid")
    for args in (["--help"], ["plan", "list", "--help"]):
        result = runner.invoke(custom, args)
        assert result.exit_code == 0, result.output
    factory.assert_not_called()


def test_repeated_invocations_reload_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom = build_cli()
    args = ["plan", "list", "-P", str(project)]
    first = runner.invoke(custom, args)
    assert first.exit_code == 0
    assert not first.stdout.startswith("{")
    monkeypatch.setenv("MACHI_AI_AGENT", "claude-code")
    second = runner.invoke(custom, args)
    assert second.exit_code == 0
    assert PlanListResult.model_validate_json(second.stdout).plans == []
