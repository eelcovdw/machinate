from pathlib import PurePosixPath
from typing import cast

from upath import UPath


class StorageError(Exception):
    def __init__(self, path: PurePosixPath | UPath, reason: Exception) -> None:
        self.path: PurePosixPath | UPath = path
        self.reason: Exception = reason
        super().__init__(f"{path}: {reason}")
        # Notes on the reason (e.g. leftover temporary files) stay visible on the wrapper.
        notes = cast("list[object] | tuple[object, ...]", getattr(reason, "__notes__", ()))
        for note in notes:
            self.add_note(str(note))


class MissingDocumentError(StorageError):
    pass


class SymbolicLinkError(StorageError):
    pass


class DocumentExistsError(StorageError):
    pass


class InvalidDocumentError(StorageError):
    pass
