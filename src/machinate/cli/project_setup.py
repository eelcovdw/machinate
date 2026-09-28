from dataclasses import dataclass
from pathlib import Path

from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.plan import PlanService
from machinate.services.search import SearchService
from machinate.services.task import TaskService
from machinate.storage import DocumentStore, Layout, ProjectState, ProjectStateStore
from machinate.storage.models import NameInput

from .models import ProjectScope


class ProjectError(Exception):
    pass


@dataclass
class ProjectContext:
    project: ProjectScope
    plans: PlanService
    tasks: TaskService
    contexts: ContextService
    docs: DocService
    search: SearchService


def select_project_directory(explicit: Path | None) -> Path:
    start = (explicit if explicit is not None else Path.cwd()).absolute()
    candidates = (start,) if explicit is not None else (start, *start.parents)
    for directory in candidates:
        storage = directory / ".machi"
        if not storage.exists() and not storage.is_symlink():
            continue
        if not storage.is_dir():
            msg = f"{storage}: expected a directory"
            raise ProjectError(msg)
        return directory
    raise ProjectError(
        f"No initialized project at {start}"
        if explicit is not None
        else f"No initialized project found from {start} upward; use -P DIRECTORY"
    )


def initialize_project(explicit: Path | None, project_name: str | None = None) -> ProjectScope:
    """Initialize the target directory as a Machinate project.

    The target is the explicit directory or the current directory; it is never
    discovered. Validation happens before any files are created.
    """
    target = (explicit if explicit is not None else Path.cwd()).absolute()
    if not target.is_dir():
        msg = f"{target}: project directory does not exist"
        raise ProjectError(msg)
    name = NameInput(name=project_name if project_name is not None else target.name).name
    storage = target / ".machi"
    if storage.exists() or storage.is_symlink():
        if not storage.is_dir():
            msg = f"{storage}: expected a directory"
            raise ProjectError(msg)
        if next(storage.iterdir(), None) is not None:
            msg = f"{storage}: already initialized or nonempty; refusing to overwrite"
            raise ProjectError(msg)
    state_store = ProjectStateStore(storage / "machinate.toml")
    state_store.write(ProjectState(project_name=name, current_plan=None))
    return ProjectScope(name=name, directory=target, storage=storage)


def prepare_project(explicit: Path | None = None) -> ProjectContext:
    directory = select_project_directory(explicit)
    storage = directory / ".machi"
    state_store = ProjectStateStore(storage / "machinate.toml")
    state = state_store.read()
    layout = Layout()
    document_store = DocumentStore(storage)
    return ProjectContext(
        project=ProjectScope(name=state.project_name, directory=directory, storage=storage),
        plans=PlanService(document_store, layout, state_store),
        tasks=TaskService(document_store, layout),
        contexts=ContextService(document_store, layout),
        docs=DocService(document_store, layout),
        search=SearchService(document_store, layout),
    )
