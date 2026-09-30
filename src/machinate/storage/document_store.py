import stat
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path, PurePosixPath

from machinate.models.documents import (
    RELATIVE_PATH_ADAPTER,
    DocumentRecord,
    Metadata,
    ParsedDocument,
)
from machinate.models.operations import DocumentQuery

from .atomic import atomic_create, atomic_write
from .errors import (
    DocumentExistsError,
    InvalidDocumentError,
    MissingDocumentError,
    StorageError,
    SymbolicLinkError,
)
from .models import DocumentCollection, FileStat


class DocumentStore:
    def __init__(self, root: Path) -> None:
        self.root: Path = root

    def read[M: Metadata](
        self, path: str | PurePosixPath, metadata_type: type[M]
    ) -> ParsedDocument[M]:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError

        relative = RELATIVE_PATH_ADAPTER.validate_python(path)
        text = self.read_text(relative)
        try:
            lines = text.splitlines(keepends=True)
            if not lines or lines[0].rstrip("\r\n") != "---":
                return self._document_from_data(relative, None, metadata_type, body=text)
            end = next((i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"), None)
            if end is None:
                raise ValueError("Unterminated YAML frontmatter")  # noqa: TRY301 - raised into the handler below
            data: object = YAML(typ="safe").load("".join(lines[1:end]))  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            return self._document_from_data(
                relative,
                data,  # pyright: ignore[reportUnknownArgumentType]
                metadata_type,
                body="".join(lines[end + 1 :]),
            )
        except (ValueError, YAMLError) as exc:
            raise InvalidDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def _document_from_data[M: Metadata](
        self, relative: PurePosixPath, data: object, metadata_type: type[M], *, body: str
    ) -> ParsedDocument[M]:
        """Validate frontmatter, defaulting created to the file mtime only when absent."""
        if data is None:
            modified = (self.root / relative).stat().st_mtime
            data = {"created_at": datetime.fromtimestamp(modified, UTC)}
        return ParsedDocument[metadata_type](metadata=metadata_type.model_validate(data), body=body)

    def list_files(self, path: str | PurePosixPath, patterns: list[str]) -> list[PurePosixPath]:
        """Return store-relative regular files under path matching any GLOBSTAR pattern."""
        relative = RELATIVE_PATH_ADAPTER.validate_python(path)
        directory = self.root / relative
        if not directory.is_dir():
            return []
        try:
            return [
                PurePosixPath(match.relative_to(self.root).as_posix())
                for match in _glob_regular_files(directory, patterns)
            ]
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def read_text(self, path: str | PurePosixPath) -> str:
        """Read a document's raw text, including any frontmatter, without parsing it."""
        relative = RELATIVE_PATH_ADAPTER.validate_python(path)
        try:
            return (self.root / relative).read_bytes().decode("utf-8-sig")
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except UnicodeDecodeError as exc:
            raise InvalidDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def _encode[M: Metadata](self, path: PurePosixPath, document: ParsedDocument[M]) -> bytes:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError

        try:
            output = StringIO()
            yaml = YAML(typ="safe")
            yaml.default_flow_style = False
            yaml.dump(document.metadata.model_dump(), output)  # pyright: ignore[reportUnknownMemberType]
            return f"---\n{output.getvalue()}---\n{document.body}".encode()
        except (ValueError, YAMLError) as exc:
            raise InvalidDocumentError(path, exc) from exc

    def create[M: Metadata](self, path: str | PurePosixPath, document: ParsedDocument[M]) -> None:
        relative = RELATIVE_PATH_ADAPTER.validate_python(path)
        content = self._encode(relative, document)
        target = self.root / relative
        try:
            if self._case_conflict(relative):
                message = f"{relative} differs only by case"
                raise FileExistsError(message)  # noqa: TRY301 - raised into the handler below
            atomic_create(target, content)
        except FileExistsError as exc:
            raise DocumentExistsError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def _case_conflict(self, relative: PurePosixPath) -> bool:
        """Return whether any component already exists under a different case.

        Checked before any directory is created, so a rejected create cannot leave an
        empty case-variant directory behind and a plan name cannot differ only by case.
        """
        current = self.root
        for part in relative.parts:
            if not current.is_dir():
                return False
            folded = part.casefold()
            try:
                entries = list(current.iterdir())
            except FileNotFoundError:
                return False
            if any(child.name != part and child.name.casefold() == folded for child in entries):
                return True
            current = current / part
        return False

    def write[M: Metadata](self, path: str | PurePosixPath, document: ParsedDocument[M]) -> None:
        relative = RELATIVE_PATH_ADAPTER.validate_python(path)
        content = self._encode(relative, document)
        target = self.root / relative
        try:
            info = target.lstat()  # Updates must not silently create missing documents.
            if stat.S_ISLNK(info.st_mode):
                # A rename would replace the link itself; refuse rather than rewrite it.
                # No underlying OS error, so no fabricated reason.
                raise SymbolicLinkError(relative)
            if not stat.S_ISREG(info.st_mode):
                raise IsADirectoryError(str(target))
            atomic_write(target, content, mode=stat.S_IMODE(info.st_mode))
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def stat(self, path: str | PurePosixPath) -> FileStat:
        relative = RELATIVE_PATH_ADAPTER.validate_python(path)
        try:
            info = (self.root / relative).stat()
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError("Expected a regular file or directory")  # noqa: TRY301 - raised into the handler below
            return FileStat(
                path=relative,
                modified_at=datetime.fromtimestamp(info.st_mtime, UTC),
            )
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except (OSError, ValueError) as exc:
            raise StorageError(relative, exc) from exc

    def absolute_path(self, path: str | PurePosixPath) -> Path:
        """Resolve a store-relative path against the store root."""
        return self.root / RELATIVE_PATH_ADAPTER.validate_python(path)

    def is_directory(self, path: str | PurePosixPath) -> bool:
        """Report whether a store-relative path is an existing directory."""
        return (self.root / RELATIVE_PATH_ADAPTER.validate_python(path)).is_dir()

    def _list_collection_files(self, collection: DocumentCollection) -> list[FileStat]:
        try:
            directory = self.root / collection.path
            if not directory.exists():
                return []
            if not directory.is_dir():
                raise NotADirectoryError(str(directory))
            return [
                self.stat(PurePosixPath(match.relative_to(self.root).as_posix()))
                for match in _glob_regular_files(directory, [str(collection.pattern)])
            ]
        except OSError as exc:
            raise StorageError(collection.path, exc) from exc

    def read_last_activity_at(
        self, path: str | PurePosixPath, *collections: DocumentCollection
    ) -> datetime:
        """Read the newest timestamp of a document and its descendant collections."""
        record = self.stat(path)
        last_activity_at = record.modified_at
        for collection in collections:
            for child in self._list_collection_files(collection):
                last_activity_at = max(last_activity_at, child.modified_at)
        return last_activity_at

    def list[M: Metadata](
        self,
        collection: DocumentCollection,
        metadata_type: type[M],
        query: DocumentQuery | None = None,
    ) -> list[DocumentRecord[M]]:
        """Glob, parse, and filter a collection; ordering and limits are the caller's."""
        query = query or DocumentQuery()
        matching_documents: list[DocumentRecord[M]] = []
        for file_metadata in self._list_collection_files(collection):
            document = self.read(file_metadata.path, metadata_type)
            name = (
                file_metadata.path.parent.name
                if collection.name_source == "parent"
                else file_metadata.path.relative_to(collection.path).with_suffix("").as_posix()
            )
            if query.matches(document.metadata):
                matching_documents.append(
                    DocumentRecord[M].from_document(
                        document,
                        name=name,
                        path=file_metadata.path,
                        modified_at=file_metadata.modified_at,
                    )
                )
        return matching_documents

    def count_documents(self, collection: DocumentCollection) -> int:
        """Count a collection's files without parsing any of them."""
        return len(self._list_collection_files(collection))


def _glob_regular_files(directory: Path, patterns: list[str]) -> list[Path]:
    """Glob patterns under directory, keeping regular files inside the base directory.

    Dot-files and files under dot-directories are skipped, so listings, counts, and
    search all use one discovery rule.
    """
    files: list[Path] = []
    base = directory.resolve()
    for pattern in patterns:
        for match in directory.glob(pattern):
            try:
                match.resolve().relative_to(base)
                relative = match.relative_to(directory)
            except ValueError:
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            if match.is_file():
                files.append(match)
    return files
