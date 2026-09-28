import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.models import ErrorResult, InitResult, ProjectScope
from machinate.storage import ProjectState, ProjectStateStore

runner = CliRunner()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MACHI_FORMAT", "MACHI_AUTOMATION", "MACHI_AGENT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def target(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    directory.mkdir()
    return directory


def read_state(directory: Path) -> ProjectState:
    return ProjectStateStore(directory / ".machi/machinate.toml").read()


def snapshot(directory: Path) -> dict[Path, tuple[bytes | None, int]]:
    return {
        path: (path.read_bytes() if path.is_file() else None, path.lstat().st_mtime_ns)
        for path in directory.rglob("*")
    }


def test_init_current_directory(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(target)
    result = runner.invoke(app, ["init", "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = InitResult.model_validate(json.loads(result.stdout))
    assert parsed.command == "init"
    assert parsed.project.name == target.name
    assert parsed.project.directory == target
    assert parsed.project.storage == target / ".machi"
    state = read_state(target)
    assert state.project_name == target.name
    assert state.current_plan is None


def test_init_explicit_project_uses_exact_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "parent"
    target = parent / "child"
    target.mkdir(parents=True)
    monkeypatch.chdir(parent)
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert (target / ".machi/machinate.toml").exists()
    assert not (parent / ".machi").exists()


def test_init_does_not_discover_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    assert runner.invoke(app, ["init", "-P", str(parent)]).exit_code == 0
    before = read_state(parent)
    child = parent / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    result = runner.invoke(app, ["init", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_state(child).project_name == child.name
    assert read_state(parent) == before


def test_init_explicit_name(target: Path) -> None:
    result = runner.invoke(app, ["init", "-P", str(target), "--project-name", "custom"])
    assert result.exit_code == 0, result.output
    assert read_state(target).project_name == "custom"


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_init_missing_project_directory(tmp_path: Path, kind: str) -> None:
    target = tmp_path / "missing"
    if kind == "file":
        target.write_text("not a directory")
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "does not exist" in ErrorResult.model_validate_json(result.stderr).error
    assert not target.is_dir()


def test_init_text_output(target: Path) -> None:
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "text"])
    assert result.exit_code == 0, result.output
    assert f"Initialized {target.name} at {target}" in result.stdout
    assert str(target / ".machi") in result.stdout
    assert not result.stdout.startswith("{")


def test_init_explicit_format_overrides_invalid_env_format(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "human")
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{")
    assert (target / ".machi").exists()


def test_init_delegation(target: Path) -> None:
    scope = ProjectScope(name="injected", directory=target, storage=target / ".machi")
    fake = Mock(return_value=scope)
    custom = create_cli(Dependencies(initialize_project=fake))
    result = runner.invoke(
        custom, ["init", "-P", str(target), "--project-name", "injected", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    fake.assert_called_once_with(target, "injected")
