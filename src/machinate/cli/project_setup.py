import os
from dataclasses import dataclass
from pathlib import Path

from machinate.models.documents import NAME_ADAPTER
from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.overview import OverviewService
from machinate.services.plan import PlanService
from machinate.services.search import SearchService
from machinate.services.task import TaskService
from machinate.storage.document_store import DocumentStore
from machinate.storage.errors import StorageError
from machinate.storage.layout import Layout
from machinate.storage.models import ProjectEntry, ProjectRedirect, ProjectState
from machinate.storage.project_state_store import ProjectStateStore

from .models import ProjectScope


class ProjectError(Exception):
    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint: str | None = hint


@dataclass
class ResolvedProject:
    directory: Path
    state: ProjectState
    state_store: ProjectStateStore


@dataclass
class InitializedRedirect:
    project: ProjectScope
    redirected_from: Path


@dataclass
class ProjectServices:
    project: ProjectScope
    plans: PlanService
    tasks: TaskService
    contexts: ContextService
    docs: DocService
    overviews: OverviewService
    search: SearchService


def resolve_project(explicit: Path | None) -> ResolvedProject:
    """Locate a project directory, following at most one ``project_dir`` redirect."""
    start = (explicit if explicit is not None else Path.cwd()).absolute()
    candidates = (start,) if explicit is not None else (start, *start.parents)
    for directory in candidates:
        store_directory = directory / ".machi"
        if not store_directory.exists() and not store_directory.is_symlink():
            continue
        if not store_directory.is_dir():
            msg = f"{store_directory}: expected a directory"
            raise ProjectError(msg)
        state_store = ProjectStateStore(store_directory / "machinate.toml")
        return _follow_redirect(directory, state_store, state_store.read_entry())
    raise ProjectError(
        f"No initialized project at {start}"
        if explicit is not None
        else f"No initialized project found from {start} upward; use -P DIRECTORY"
    )


def _follow_redirect(
    directory: Path, state_store: ProjectStateStore, entry: ProjectEntry
) -> ResolvedProject:
    if not isinstance(entry, ProjectRedirect):
        return ResolvedProject(directory=directory, state=entry, state_store=state_store)
    target = Path(os.path.normpath(directory / entry.project_dir.expanduser()))
    return _read_redirect_target(state_store.path, target)


def _read_redirect_target(source: Path, target: Path) -> ResolvedProject:
    """Load the project a redirect points at.

    ``source`` names the redirect file for error messages. Rejects a missing,
    uninitialized, or redirecting target; shared by reading and writing redirects.
    """
    target_store = ProjectStateStore(target / ".machi" / "machinate.toml")
    try:
        entry = target_store.read_entry()
    except StorageError as exc:
        msg = f"{source}: project_dir points at {target}, which is not an initialized project"
        raise ProjectError(
            msg, hint="Fix project_dir or run 'machi init' in the target directory."
        ) from exc
    if isinstance(entry, ProjectRedirect):
        msg = (
            f"{source}: project_dir points at {target}, "
            "which is itself a redirect; only one hop is allowed"
        )
        raise ProjectError(
            msg, hint="Point project_dir at the directory that holds the shared store."
        )
    return ResolvedProject(directory=target, state=entry, state_store=target_store)


def _prepare_store_directory(target: Path) -> Path:
    """Validate an init target and return its still-empty ``.machi`` directory.

    Shared by plain and redirect init so the target and empty-store checks cannot
    drift apart. Raises before any file is written.
    """
    if not target.is_dir():
        msg = f"{target}: project directory does not exist"
        raise ProjectError(msg)
    store_directory = target / ".machi"
    if store_directory.exists() or store_directory.is_symlink():
        if not store_directory.is_dir():
            msg = f"{store_directory}: expected a directory"
            raise ProjectError(msg)
        if next(store_directory.iterdir(), None) is not None:
            msg = f"{store_directory}: already initialized or nonempty; refusing to overwrite"
            raise ProjectError(msg)
    return store_directory


def initialize_project(explicit: Path | None, project_name: str | None = None) -> ProjectScope:
    """Initialize the target directory as a Machinate project.

    The target is the explicit directory or the current directory; it is never
    discovered. Validation happens before any files are created.
    """
    target = (explicit if explicit is not None else Path.cwd()).absolute()
    store_directory = _prepare_store_directory(target)
    name = NAME_ADAPTER.validate_python(project_name if project_name is not None else target.name)
    state_store = ProjectStateStore(store_directory / "machinate.toml")
    state_store.write(ProjectState(project_name=name, current_plan=None))
    return ProjectScope(name=name, directory=target, store_directory=store_directory)


def initialize_redirect(explicit: Path | None, redirect: Path) -> InitializedRedirect:
    """Write a redirect to an existing project instead of creating a new store.

    ``redirect`` is a CLI path, so a relative value resolves against the current
    directory. It is stored relative to the directory being initialized, so the file
    still works from another checkout; an absolute or ``~`` value is stored as given.
    """
    target = (explicit if explicit is not None else Path.cwd()).absolute()
    store_directory = _prepare_store_directory(target)
    redirect_expanded = redirect.expanduser()
    # A quoted `~/...` survives worktrees and other users' homes; keep it as typed.
    is_stored_as_given = redirect.is_absolute() or redirect_expanded != redirect
    if not redirect_expanded.is_absolute():
        redirect_expanded = Path.cwd() / redirect_expanded
    redirect_absolute = Path(os.path.normpath(redirect_expanded))
    resolved = _read_redirect_target(store_directory / "machinate.toml", redirect_absolute)
    stored = redirect if is_stored_as_given else Path(os.path.relpath(redirect_absolute, target))
    ProjectStateStore(store_directory / "machinate.toml").write(ProjectRedirect(project_dir=stored))
    return InitializedRedirect(
        project=ProjectScope(
            name=resolved.state.project_name,
            directory=resolved.directory,
            store_directory=resolved.directory / ".machi",
        ),
        redirected_from=target,
    )


def open_project(explicit: Path | None = None) -> ProjectServices:
    resolved = resolve_project(explicit)
    directory = resolved.directory
    store_directory = directory / ".machi"
    state_store = resolved.state_store
    state = resolved.state
    layout = Layout()
    document_store = DocumentStore(store_directory)
    plans = PlanService(document_store, layout, state_store)
    tasks = TaskService(document_store, layout)
    contexts = ContextService(document_store, layout)
    docs = DocService(document_store, layout)
    return ProjectServices(
        project=ProjectScope(
            name=state.project_name, directory=directory, store_directory=store_directory
        ),
        plans=plans,
        tasks=tasks,
        contexts=contexts,
        docs=docs,
        overviews=OverviewService(plans, tasks, contexts, docs),
        search=SearchService(document_store, layout, plans),
    )
