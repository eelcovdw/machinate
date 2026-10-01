import tomllib
from pathlib import Path

import tomli_w
from pydantic import ValidationError

from .atomic import atomic_write, existing_mode
from .errors import InvalidDocumentError, MissingDocumentError, StorageError
from .models import ProjectEntry, ProjectRedirect, ProjectState


class ProjectStateStore:
    def __init__(self, path: Path) -> None:
        self.path: Path = path

    def _load(self) -> dict[str, object]:
        try:
            return tomllib.loads(self.path.read_bytes().decode("utf-8-sig"))
        except FileNotFoundError as exc:
            raise MissingDocumentError(self.path, exc) from exc
        except ValueError as exc:
            raise InvalidDocumentError(self.path, exc) from exc
        except OSError as exc:
            raise StorageError(self.path, exc) from exc

    def read(self) -> ProjectState:
        try:
            return ProjectState.model_validate(self._load())
        except ValidationError as exc:
            raise InvalidDocumentError(self.path, exc) from exc

    def read_entry(self) -> ProjectEntry:
        """Read the state file as its declared shape: real state or a redirect."""
        data = self._load()
        try:
            if "project_dir" in data:
                return ProjectRedirect.model_validate(data)
            return ProjectState.model_validate(data)
        except ValidationError as exc:
            raise InvalidDocumentError(self.path, exc) from exc

    def write(self, state: ProjectState) -> None:
        try:
            content = tomli_w.dumps(state.model_dump(exclude_none=True)).encode("utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Preserve permissions on update; fresh files use the umask default like
            # documents, so the state file is not a special owner-only case.
            atomic_write(self.path, content, mode=existing_mode(self.path))
        except OSError as exc:
            raise StorageError(self.path, exc) from exc
