from pathlib import Path

import pytest
from harness import cli, make_settings, read_state

from machinate.cli.dependencies import Dependencies
from machinate.cli.models import InitResult


@pytest.fixture
def target(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    directory.mkdir()
    return directory


def test_init_current_directory(
    target: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(target)
    parsed = cli.json(InitResult, ["init", "--format", "json"])
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
    cli.json(InitResult, ["init", "-P", str(target), "--format", "json"])
    assert (target / ".machi/machinate.toml").exists()
    assert not (parent / ".machi").exists()


def test_init_does_not_discover_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    assert cli.run(["init", "-P", str(parent)]).exit_code == 0
    before = read_state(parent)
    child = parent / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    cli.json(InitResult, ["init", "--format", "json"])
    assert read_state(child).project_name == child.name
    assert read_state(parent) == before


def test_init_explicit_name(target: Path) -> None:
    cli.run(["init", "-P", str(target), "--project-name", "custom"])
    assert read_state(target).project_name == "custom"


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_init_missing_project_directory(tmp_path: Path, kind: str) -> None:
    target = tmp_path / "missing"
    if kind == "file":
        target.write_text("not a directory")
    error = cli.error(["init", "-P", str(target), "--format", "json"])
    assert error.command == "init"
    assert not target.is_dir()


def test_init_text_smoke(target: Path) -> None:
    result = cli.run(["init", "-P", str(target), "--format", "text"])
    assert result.exit_code == 0
    assert target.name in result.stdout


def test_init_explicit_format_overrides_invalid_env_format(target: Path) -> None:
    dependencies = Dependencies(settings=make_settings(format_name="human"))
    parsed = cli.json(
        InitResult,
        ["init", "-P", str(target), "--format", "json"],
        dependencies=dependencies,
    )
    assert parsed.command == "init"
    assert (target / ".machi").exists()
