import json
from pathlib import Path
from typing import override
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner
from upath import UPath

from machinate.cli.cli import app, create_cli
from machinate.cli.dependencies import Dependencies
from machinate.cli.formatting import Formatter
from machinate.cli.models import CommandResult, ErrorResult, InitResult, ListResult, ProjectScope
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
    return ProjectStateStore(UPath(directory / ".machi/machinate.toml")).read()


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


def test_init_empty_machi_directory_allowed(target: Path) -> None:
    (target / ".machi").mkdir()
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert read_state(target).project_name == target.name


def test_init_symlinked_storage(target: Path) -> None:
    external = target / "external"
    external.mkdir()
    (target / ".machi").symlink_to(external, target_is_directory=True)
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert (external / "machinate.toml").exists()
    assert read_state(target).project_name == target.name


@pytest.mark.parametrize("kind", ["symlink-file", "symlink-dangling", "file"])
def test_init_rejects_non_directory_storage(target: Path, kind: str) -> None:
    storage = target / ".machi"
    if kind == "file":
        storage.write_text("keep")
    elif kind == "symlink-file":
        target_file = target / "target-file"
        target_file.write_text("keep")
        storage.symlink_to(target_file)
    else:
        storage.symlink_to(target / "nowhere", target_is_directory=True)
    before = snapshot(target)
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 1, result.output
    assert "expected a directory" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(target) == before


def test_init_already_initialized_preserves_state(target: Path) -> None:
    assert runner.invoke(app, ["init", "-P", str(target), "--project-name", "first"]).exit_code == 0
    before = snapshot(target)
    state_before = read_state(target)
    result = runner.invoke(
        app, ["init", "-P", str(target), "--project-name", "second", "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert "already initialized or nonempty" in ErrorResult.model_validate_json(result.stderr).error
    assert snapshot(target) == before
    assert read_state(target) == state_before
    assert read_state(target).project_name == "first"


def test_init_nonempty_storage_preserves_files(target: Path) -> None:
    storage = target / ".machi"
    storage.mkdir()
    keep = storage / "keep.txt"
    keep.write_text("precious")
    before = snapshot(target)
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 1, result.output
    error = ErrorResult.model_validate_json(result.stderr)
    assert "already initialized or nonempty" in error.error
    assert keep.read_text() == "precious"
    assert snapshot(target) == before
    assert not (storage / "machinate.toml").exists()


@pytest.mark.parametrize("name", ["bad/name", "bad\\name", "", ".", "..", "has:colon"])
def test_init_invalid_name_preserves_target(target: Path, name: str) -> None:
    before = snapshot(target)
    result = runner.invoke(
        app, ["init", "-P", str(target), "--project-name", name, "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    assert ErrorResult.model_validate_json(result.stderr).error
    assert not (target / ".machi").exists()
    assert snapshot(target) == before


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


@pytest.mark.parametrize(
    ("automation", "env_format", "flag", "expected"),
    [
        (None, None, None, "text"),
        ("true", None, None, "json"),
        ("false", None, None, "text"),
        (None, "json", None, "json"),
        ("true", "json", "text", "text"),
    ],
)
def test_init_format_precedence(  # noqa: PLR0913
    target: Path,
    monkeypatch: pytest.MonkeyPatch,
    automation: str | None,
    env_format: str | None,
    flag: str | None,
    expected: str,
) -> None:
    if automation is not None:
        monkeypatch.setenv("MACHI_AUTOMATION", automation)
    if env_format is not None:
        monkeypatch.setenv("MACHI_FORMAT", env_format)
    args = ["init", "-P", str(target)]
    if flag is not None:
        args.extend(["--format", flag])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{") == (expected == "json")


@pytest.mark.parametrize(
    ("env_name", "env_value", "field"),
    [
        ("MACHI_AUTOMATION", "perhaps", "automation"),
        ("MACHI_FORMAT", "human", "format"),
    ],
)
def test_init_invalid_settings(
    target: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    env_value: str,
    field: str,
) -> None:
    monkeypatch.setenv(env_name, env_value)
    result = runner.invoke(app, ["init", "-P", str(target)])
    assert result.exit_code == 1
    assert field in ErrorResult.model_validate_json(result.stderr).error
    assert not (target / ".machi").exists()


def test_init_explicit_format_overrides_invalid_env_format(
    target: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MACHI_FORMAT", "human")
    result = runner.invoke(app, ["init", "-P", str(target), "--format", "json"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("{")
    assert (target / ".machi").exists()


class ReplacementFormatter(Formatter):
    def __init__(self) -> None:
        self.results: list[CommandResult] = []

    @override
    def format(self, result: CommandResult) -> str:
        self.results.append(result)
        return "replacement"


def test_init_formatter_injection(target: Path) -> None:
    formatter = ReplacementFormatter()
    custom = create_cli(Dependencies(formatters={"custom": formatter}))
    result = runner.invoke(custom, ["init", "-P", str(target), "--format", "custom"])
    assert result.exit_code == 0
    assert result.stdout == "replacement\n"
    assert isinstance(formatter.results[0], InitResult)
    missing = target / "missing"
    result = runner.invoke(custom, ["init", "-P", str(missing), "--format", "custom"])
    assert result.exit_code == 1
    assert result.stderr == "replacement\n"
    assert isinstance(formatter.results[1], ErrorResult)


def test_init_delegation(target: Path) -> None:
    scope = ProjectScope(name="injected", directory=target, storage=target / ".machi")
    fake = Mock(return_value=scope)
    custom = create_cli(Dependencies(initialize_project=fake))
    result = runner.invoke(
        custom, ["init", "-P", str(target), "--project-name", "injected", "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    fake.assert_called_once_with(target, "injected")


def test_init_then_list_is_empty(target: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(target)
    assert runner.invoke(app, ["init", "--format", "json"]).exit_code == 0
    result = runner.invoke(app, ["plan", "list", "--format", "json"])
    assert result.exit_code == 0, result.output
    parsed = ListResult.model_validate(json.loads(result.stdout))
    assert parsed.plans == []
    assert parsed.project.name == target.name
    assert parsed.project.directory == target


@pytest.mark.parametrize("invalid", [["--project-name"], ["--unknown"]])
@pytest.mark.parametrize("source", ["flag", "environment", "automation"])
def test_init_parser_errors_use_json(
    invalid: list[str],
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = ["init"]
    if source == "flag":
        args.extend(["--format", "json"])
    elif source == "environment":
        monkeypatch.setenv("MACHI_FORMAT", "json")
    else:
        monkeypatch.setenv("MACHI_AUTOMATION", "true")
    result = runner.invoke(app, [*args, *invalid])
    assert result.exit_code == 2
    assert result.stdout == ""
    parsed = ErrorResult.model_validate_json(result.stderr)
    assert parsed.command == "init"
    assert invalid[0] in parsed.error
