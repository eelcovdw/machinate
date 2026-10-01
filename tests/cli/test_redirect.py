"""Following a project_dir redirect from discovery and an explicit -P path."""

from pathlib import Path

import pytest
from harness import cli

from machinate.cli.dependencies import Dependencies
from machinate.cli.models import InitResult, PlanListResult
from machinate.cli.project_setup import ProjectError, open_project
from machinate.cli.settings import Settings
from machinate.storage import InvalidDocumentError, ProjectState, ProjectStateStore, StorageError


def init_project(directory: Path) -> Path:
    ProjectStateStore(directory / ".machi/machinate.toml").write(
        ProjectState(project_name=directory.name)
    )
    return directory


def make_redirect(repo: Path, target: str) -> Path:
    store = repo / ".machi"
    store.mkdir(parents=True)
    (store / "machinate.toml").write_text(f'project_dir = "{target}"\n')
    return repo


def with_project_dir(directory: Path) -> Dependencies:
    """Inject settings the way a MACHI_PROJECT_DIR env var would."""
    return Dependencies(settings=Settings(project_dir=directory))


def test_discovery_follows_relative_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = init_project(tmp_path / "planning")
    repo = make_redirect(tmp_path / "repo-a", "../planning")
    nested = repo / "src/deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    project = open_project().project

    assert project.name == "planning"
    assert project.directory == real
    assert project.store_directory == real / ".machi"


def test_explicit_path_follows_redirect(tmp_path: Path) -> None:
    real = init_project(tmp_path / "planning")
    repo = make_redirect(tmp_path / "repo-a", "../planning")

    project = open_project(repo).project

    assert project.directory == real
    assert project.store_directory == real / ".machi"


def test_absolute_redirect_target(tmp_path: Path) -> None:
    real = init_project(tmp_path / "planning")
    repo = make_redirect(tmp_path / "repo-a", str(real))

    assert open_project(repo).project.directory == real


def test_missing_target_is_rejected(tmp_path: Path) -> None:
    repo = make_redirect(tmp_path / "repo-a", "../nowhere")

    with pytest.raises(ProjectError) as error:
        open_project(repo)

    assert error.value.hint is not None


def test_uninitialized_target_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "planning").mkdir()
    repo = make_redirect(tmp_path / "repo-a", "../planning")

    with pytest.raises(ProjectError):
        open_project(repo)


def test_redirect_chain_is_rejected(tmp_path: Path) -> None:
    init_project(tmp_path / "planning")
    make_redirect(tmp_path / "repo-b", "../planning")
    repo = make_redirect(tmp_path / "repo-a", "../repo-b")

    with pytest.raises(ProjectError) as error:
        open_project(repo)

    assert error.value.hint is not None


def test_mixed_keys_are_rejected(tmp_path: Path) -> None:
    init_project(tmp_path / "planning")
    store = tmp_path / "repo-a" / ".machi"
    store.mkdir(parents=True)
    (store / "machinate.toml").write_text('project_name = "repo-a"\nproject_dir = "../planning"\n')

    with pytest.raises(InvalidDocumentError):
        open_project(tmp_path / "repo-a")


def test_corrupt_local_state_keeps_storage_error(tmp_path: Path) -> None:
    store = tmp_path / "repo-a" / ".machi"
    store.mkdir(parents=True)
    (store / "machinate.toml").write_text("[")

    with pytest.raises(StorageError):
        open_project(tmp_path / "repo-a")


def test_env_var_follows_redirect(tmp_path: Path) -> None:
    real = init_project(tmp_path / "planning")
    repo = make_redirect(tmp_path / "repo-a", "../planning")

    parsed = cli.json(
        PlanListResult,
        ["plan", "list", "--format", "json"],
        dependencies=with_project_dir(repo),
    )

    assert parsed.project.directory == real
    assert parsed.project.store_directory == real / ".machi"


def test_explicit_path_beats_env_var(tmp_path: Path) -> None:
    real = init_project(tmp_path / "planning")
    other = init_project(tmp_path / "other")

    parsed = cli.json(
        PlanListResult,
        ["plan", "list", "-P", str(other), "--format", "json"],
        dependencies=with_project_dir(real),
    )

    assert parsed.project.directory == other


def test_env_var_beats_discovery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_target = init_project(tmp_path / "planning")
    repo = init_project(tmp_path / "repo-a")
    nested = repo / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)

    parsed = cli.json(
        PlanListResult,
        ["plan", "list", "--format", "json"],
        dependencies=with_project_dir(env_target),
    )

    assert parsed.project.directory == env_target


def test_init_ignores_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = init_project(tmp_path / "planning")
    target = tmp_path / "repo-a"
    target.mkdir()
    monkeypatch.chdir(target)

    parsed = cli.json(
        InitResult,
        ["init", "--format", "json"],
        dependencies=with_project_dir(shared),
    )

    assert parsed.project.directory == target
    assert parsed.project.store_directory == target / ".machi"


def test_env_var_failure_names_its_source(tmp_path: Path) -> None:
    error = cli.error(
        ["plan", "list", "--format", "json"],
        code="project",
        dependencies=with_project_dir(tmp_path / "nowhere"),
    )

    assert error.hint is not None
