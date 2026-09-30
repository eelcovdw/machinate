from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, build_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult, PlanListResult
from machinate.cli.settings import Settings

runner = CliRunner()


def test_defaults_to_text() -> None:
    settings = Settings()
    assert settings.ai_agent is None
    assert settings.is_agent_mode is False
    assert settings.format == "text"


def test_invalid_settings_reports_field(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "human")
    result = runner.invoke(app, ["plan", "list", "-P", str(project)])
    assert result.exit_code == 1
    assert "format" in ErrorResult.model_validate_json(result.stderr).error


def test_explicit_format_overrides_invalid_env_format(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "human")
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{")


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


@pytest.mark.parametrize(
    "args", [["plan", "list", "-P", "{project}"], ["plan", "list", "--unknown"]]
)
def test_settings_resolve_once_per_invocation(
    project: Path, monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    calls = 0
    real_resolve = Dependencies.resolve_settings

    def counting(self: Dependencies) -> Settings:
        nonlocal calls
        calls += 1
        return real_resolve(self)

    monkeypatch.setattr(Dependencies, "resolve_settings", counting)
    result = runner.invoke(app, [part.format(project=project) for part in args])
    assert result.exit_code in (0, 2)
    assert calls == 1
