"""Following a project_dir redirect from discovery and an explicit -P path."""

from pathlib import Path

import pytest
from harness import cli

from machinate.cli.dependencies import Dependencies
from machinate.cli.models import InitResult, PlanListResult
from machinate.cli.project_setup import ProjectError, initialize_redirect, open_project
from machinate.cli.settings import Settings
from machinate.storage import (
    InvalidDocumentError,
    ProjectState,
    ProjectStateStore,
    StorageError,
)
from machinate.storage.models import ProjectRedirect


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


def stored_redirect(repo: Path) -> ProjectRedirect:
    entry = ProjectStateStore(repo / ".machi" / "machinate.toml").read_entry()
    assert isinstance(entry, ProjectRedirect)
    return entry


def test_redirect_init_is_followed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared = init_project(tmp_path / "planning")
    repo = tmp_path / "repo-a"
    repo.mkdir()
    monkeypatch.chdir(repo)

    initialized = initialize_redirect(None, Path("../planning"))

    assert initialized.redirected_from == repo
    assert initialized.project.directory == shared
    assert stored_redirect(repo).project_dir == Path("../planning")
    assert open_project(repo).project.directory == shared


def test_relative_redirect_is_stored_relative_to_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_project(tmp_path / "planning")
    repo = tmp_path / "repo-a"
    nested = repo / "sub"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    initialize_redirect(repo, Path("../../planning"))

    assert stored_redirect(repo).project_dir == Path("../planning")


def test_absolute_redirect_stays_absolute(tmp_path: Path) -> None:
    shared = init_project(tmp_path / "planning")
    repo = tmp_path / "repo-a"
    repo.mkdir()

    initialize_redirect(repo, shared)

    assert stored_redirect(repo).project_dir == shared


def test_home_relative_redirect_is_stored_as_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    shared = init_project(tmp_path / "planning")
    repo = tmp_path / "work" / "repo-a"
    repo.mkdir(parents=True)

    initialize_redirect(repo, Path("~/planning"))

    assert stored_redirect(repo).project_dir == Path("~/planning")
    assert open_project(repo).project.directory == shared


@pytest.mark.parametrize("kind", ["missing", "uninitialized", "redirect", "nonempty"])
def test_redirect_init_refuses_bad_target(tmp_path: Path, kind: str) -> None:
    shared = init_project(tmp_path / "planning")
    repo = tmp_path / "repo-a"
    repo.mkdir()
    if kind == "missing":
        redirect = tmp_path / "nowhere"
    elif kind == "uninitialized":
        redirect = tmp_path / "empty"
        redirect.mkdir()
    elif kind == "redirect":
        redirect = make_redirect(tmp_path / "repo-b", "../planning")
    else:
        redirect = shared
        (repo / ".machi").mkdir()
        (repo / ".machi" / "keep").write_text("")

    with pytest.raises(ProjectError):
        initialize_redirect(repo, redirect)

    if kind == "nonempty":
        assert (repo / ".machi" / "keep").exists()
    else:
        assert not (repo / ".machi").exists()


def test_redirect_init_rejects_project_name(tmp_path: Path) -> None:
    shared = init_project(tmp_path / "planning")
    repo = tmp_path / "repo-a"
    repo.mkdir()

    cli.error(
        [
            "init",
            "-P",
            str(repo),
            "--redirect",
            str(shared),
            "--project-name",
            "custom",
            "--format",
            "json",
        ],
        code="input",
    )

    assert not (repo / ".machi").exists()


def test_redirect_init_wiring(tmp_path: Path) -> None:
    shared = init_project(tmp_path / "planning")
    repo = tmp_path / "repo-a"
    repo.mkdir()

    parsed = cli.json(
        InitResult,
        ["init", "-P", str(repo), "--redirect", str(shared), "--format", "json"],
    )

    assert parsed.project.directory == shared
    assert parsed.project.store_directory == shared / ".machi"
    assert parsed.redirected_from == repo
    assert open_project(repo).project.directory == shared


def test_env_var_failure_names_its_source(tmp_path: Path) -> None:
    error = cli.error(
        ["plan", "list", "--format", "json"],
        code="project",
        dependencies=with_project_dir(tmp_path / "nowhere"),
    )

    assert error.hint is not None
