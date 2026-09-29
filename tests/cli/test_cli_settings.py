from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult, ListResult
from machinate.cli.settings import Settings

runner = CliRunner()


def test_defaults_to_text() -> None:
    settings = Settings()
    assert settings.automation is False
    assert settings.format == "text"


def test_automation_defaults_to_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    settings = Settings()
    assert settings.automation is True
    assert settings.format == "json"


def test_explicit_format_beats_automation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    monkeypatch.setenv("MACHI_FORMAT", "text")
    assert Settings().format == "text"


def test_automation_false_stays_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACHI_AUTOMATION", "false")
    settings = Settings()
    assert settings.automation is False
    assert settings.format == "text"


@pytest.mark.parametrize(
    ("env_name", "env_value", "field"),
    [
        ("MACHI_AUTOMATION", "perhaps", "automation"),
        ("MACHI_FORMAT", "human", "format"),
    ],
)
def test_invalid_settings_reports_field(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["plan", "list", "-P", str(project)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error


def test_explicit_format_overrides_invalid_env_format(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "human")
    result = runner.invoke(app, ["plan", "list", "-P", str(project), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{")


def test_help_does_not_prepare_project(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = Mock(side_effect=AssertionError("help must not prepare a project"))
    custom = create_cli(Dependencies(prepare_project=factory))
    monkeypatch.setenv("MACHI_AUTOMATION", "invalid")
    for args in (["--help"], ["plan", "list", "--help"]):
        result = runner.invoke(custom, args)
        assert result.exit_code == 0, result.output
    factory.assert_not_called()


def test_repeated_invocations_reload_settings(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom = create_cli()
    args = ["plan", "list", "-P", str(project)]
    first = runner.invoke(custom, args)
    assert first.exit_code == 0
    assert not first.stdout.startswith("{")
    monkeypatch.setenv("MACHI_AUTOMATION", "true")
    second = runner.invoke(custom, args)
    assert second.exit_code == 0
    assert ListResult.model_validate_json(second.stdout).plans == []


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
