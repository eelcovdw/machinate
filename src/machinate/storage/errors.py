from pathlib import PurePosixPath

from upath import UPath


class StorageError(Exception):
    def __init__(self, path: PurePosixPath | UPath, reason: Exception) -> None:
        self.path: PurePosixPath | UPath = path
        self.reason: Exception = reason
        super().__init__(f"{path}: {reason}")


class MissingDocumentError(StorageError):
    pass


class DocumentExistsError(StorageError):
    pass


class InvalidDocumentError(StorageError):
    pass
