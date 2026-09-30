from dataclasses import dataclass
from pathlib import Path

from machinate.models.documents import NAME_ADAPTER
from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.overview import OverviewService
from machinate.services.plan import PlanService
from machinate.services.search import SearchService
from machinate.services.task import TaskService
from machinate.storage import DocumentStore, Layout, ProjectState, ProjectStateStore

from .models import ProjectScope


class ProjectError(Exception):
    pass


@dataclass
class ProjectServices:
    project: ProjectScope
    plans: PlanService
    tasks: TaskService
    contexts: ContextService
    docs: DocService
    overviews: OverviewService
    search: SearchService


def discover_project_directory(explicit: Path | None) -> Path:
    start = (explicit if explicit is not None else Path.cwd()).absolute()
    candidates = (start,) if explicit is not None else (start, *start.parents)
    for directory in candidates:
        store_directory = directory / ".machi"
        if not store_directory.exists() and not store_directory.is_symlink():
            continue
        if not store_directory.is_dir():
            msg = f"{store_directory}: expected a directory"
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
    name = NAME_ADAPTER.validate_python(project_name if project_name is not None else target.name)
    store_directory = target / ".machi"
    if store_directory.exists() or store_directory.is_symlink():
        if not store_directory.is_dir():
            msg = f"{store_directory}: expected a directory"
            raise ProjectError(msg)
        if next(store_directory.iterdir(), None) is not None:
            msg = f"{store_directory}: already initialized or nonempty; refusing to overwrite"
            raise ProjectError(msg)
    state_store = ProjectStateStore(store_directory / "machinate.toml")
    state_store.write(ProjectState(project_name=name, current_plan=None))
    return ProjectScope(name=name, directory=target, store_directory=store_directory)


def open_project(explicit: Path | None = None) -> ProjectServices:
    directory = discover_project_directory(explicit)
    store_directory = directory / ".machi"
    state_store = ProjectStateStore(store_directory / "machinate.toml")
    state = state_store.read()
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
