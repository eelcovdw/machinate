import stat
from dataclasses import dataclass
from pathlib import Path

from upath import UPath

from machinate.services.plan import PlanService
from machinate.storage import DocumentStore, Layout, ProjectStateStore

from .models import ProjectScope


class ProjectError(Exception):
    pass


@dataclass
class ProjectContext:
    project: ProjectScope
    plans: PlanService


def select_project_directory(explicit: Path | None) -> Path:
    start = (explicit if explicit is not None else Path.cwd()).absolute()
    candidates = (start,) if explicit is not None else (start, *start.parents)
    for directory in candidates:
        storage = directory / ".machi"
        try:
            mode = storage.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            msg = f"{storage}: expected a real .machi directory, not a symlink"
            raise ProjectError(msg)
        if not stat.S_ISDIR(mode):
            msg = f"{storage}: expected a directory"
            raise ProjectError(msg)
        return directory
    raise ProjectError(
        f"No initialized project at {start}"
        if explicit is not None
        else f"No initialized project found from {start} upward; use -P DIRECTORY"
    )


def prepare_project(explicit: Path | None = None) -> ProjectContext:
    directory = select_project_directory(explicit)
    storage = directory / ".machi"
    state_store = ProjectStateStore(UPath(storage / "machinate.toml"))
    state = state_store.read()
    layout = Layout()
    return ProjectContext(
        project=ProjectScope(name=state.project_name, directory=directory, storage=storage),
        plans=PlanService(DocumentStore(UPath(storage)), layout, state_store),
    )
