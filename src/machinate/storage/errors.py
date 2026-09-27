from pathlib import PurePosixPath
from typing import cast

from upath import UPath


class StorageError(Exception):
    def __init__(
        self,
        path: PurePosixPath | UPath,
        reason: Exception | None = None,
        *,
        message: str | None = None,
    ) -> None:
        self.path: PurePosixPath | UPath = path
        self.reason: Exception | None = reason
        if reason is not None:
            detail = f"{path}: {reason}"
        elif message is not None:
            detail = f"{path}: {message}"
        else:
            detail = str(path)
        super().__init__(detail)
        if reason is not None:
            # Notes on the reason (e.g. leftover temporary files) stay visible on the wrapper.
            notes = cast("list[object] | tuple[object, ...]", getattr(reason, "__notes__", ()))
            for note in notes:
                self.add_note(str(note))


class MissingDocumentError(StorageError):
    pass


class SymbolicLinkError(StorageError):
    def __init__(self, path: PurePosixPath | UPath) -> None:
        super().__init__(path, message="Refusing to replace a symbolic link")


class DocumentExistsError(StorageError):
    pass


class InvalidDocumentError(StorageError):
    pass
