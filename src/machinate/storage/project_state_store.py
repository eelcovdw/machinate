import stat
import tomllib
from pathlib import Path

import tomli_w
from upath import UPath

from .atomic import atomic_write
from .errors import InvalidDocumentError, MissingDocumentError, StorageError, SymbolicLinkError
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
            content = tomli_w.dumps(state.model_dump(exclude_none=True)).encode("utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Preserve permissions on update; fresh files are 0600 (NamedTemporaryFile
            # is always owner-only), not the umask default.
            try:
                info = self.path.lstat()
            except FileNotFoundError:
                mode = None
            else:
                if stat.S_ISLNK(info.st_mode):
                    # A rename would replace the link itself; refuse rather than rewrite it.
                    # No underlying OS error, so no fabricated reason.
                    raise SymbolicLinkError(self.path)
                mode = stat.S_IMODE(info.st_mode)
            atomic_write(Path(self.path.path), content, mode=mode)
        except OSError as exc:
            raise StorageError(self.path, exc) from exc
