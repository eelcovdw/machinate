import tomllib

import tomli_w
from upath import UPath

from .errors import InvalidDocumentError, MissingDocumentError, StorageError
from .models import ProjectState


class ProjectStateStore:
    def __init__(self, path: UPath) -> None:
        self.path: UPath = path

    def read(self) -> ProjectState:
        try:
            return ProjectState.model_validate(
                tomllib.loads(self.path.read_bytes().decode("utf-8"))
            )
        except FileNotFoundError as exc:
            raise MissingDocumentError(self.path, exc) from exc
        except ValueError as exc:
            raise InvalidDocumentError(self.path, exc) from exc
        except OSError as exc:
            raise StorageError(self.path, exc) from exc

    def write(self, state: ProjectState) -> None:
        try:
            content = tomli_w.dumps(state.model_dump(exclude_none=True))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_bytes(content.encode("utf-8"))
        except OSError as exc:
            raise StorageError(self.path, exc) from exc
