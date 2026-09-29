import stat
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path, PurePosixPath
from typing import cast

from .atomic import atomic_create, atomic_write
from .errors import (
    DocumentExistsError,
    InvalidDocumentError,
    MissingDocumentError,
    StorageError,
    SymbolicLinkError,
)
from .models import Document, FileMetadata, Metadata, PathInput, StatusMetadata
from .queries import DocumentCollection, DocumentQuery, DocumentRecord, DocumentScope, StatusQuery


class DocumentStore:
    def __init__(self, root: Path) -> None:
        self.root: Path = root

    def read[M: Metadata](self, path: str | PurePosixPath, metadata_type: type[M]) -> Document[M]:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError

        relative = PathInput.model_validate({"path": path}).path
        try:
            # Decode bytes directly so universal-newline translation cannot alter the body.
            # utf-8-sig strips a BOM that editors commonly add on Windows.
            text = (self.root / relative).read_bytes().decode("utf-8-sig")
            lines = text.splitlines(keepends=True)
            if not lines or lines[0].rstrip("\r\n") != "---":
                document = self._without_frontmatter(relative, text, metadata_type)
            else:
                end = next(
                    (i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"), None
                )
                if end is None:
                    raise ValueError("Unterminated YAML frontmatter")  # noqa: TRY301
                data: object = YAML(typ="safe").load("".join(lines[1:end]))  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                document = self._document_from_data(
                    relative,
                    data,  # pyright: ignore[reportUnknownArgumentType]
                    metadata_type,
                    body="".join(lines[end + 1 :]),
                )
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except (ValueError, YAMLError) as exc:
            raise InvalidDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc
        else:
            return document

    def _document_from_data[M: Metadata](
        self, relative: PurePosixPath, data: object, metadata_type: type[M], *, body: str
    ) -> Document[M]:
        """Validate frontmatter, defaulting created to the file mtime only when absent."""
        if data is None:
            modified = (self.root / relative).stat().st_mtime
            data = {"created": datetime.fromtimestamp(modified, UTC)}
        return Document[metadata_type](metadata=metadata_type.model_validate(data), body=body)

    def glob_files(self, path: str | PurePosixPath, patterns: list[str]) -> list[PurePosixPath]:
        """Return project-relative regular files under path matching any GLOBSTAR pattern."""
        relative = PathInput.model_validate({"path": path}).path
        directory = self.root / relative
        if not directory.is_dir():
            return []
        try:
            return [
                PurePosixPath(match.relative_to(self.root).as_posix())
                for match in _glob_regular_files(directory, patterns, include_dotfiles=True)
            ]
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def read_text(self, path: str | PurePosixPath) -> str:
        """Read a document's raw text, including any frontmatter, without parsing it."""
        relative = PathInput.model_validate({"path": path}).path
        try:
            return (self.root / relative).read_bytes().decode("utf-8-sig")
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except UnicodeDecodeError as exc:
            raise InvalidDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def _without_frontmatter[M: Metadata](
        self, relative: PurePosixPath, text: str, metadata_type: type[M]
    ) -> Document[M]:
        """Treat a file with no frontmatter block as a bare body with default metadata."""
        import logging

        logging.getLogger(__name__).debug(
            "Missing YAML frontmatter in %s; using defaults", relative
        )
        return self._document_from_data(relative, None, metadata_type, body=text)

    def _encode[M: Metadata](self, path: PurePosixPath, document: Document[M]) -> bytes:
        from ruamel.yaml import YAML
        from ruamel.yaml.error import YAMLError

        try:
            output = StringIO()
            yaml = YAML(typ="safe")
            yaml.default_flow_style = False
            # Only an authored summary is stored; derived ones are computed on demand.
            # Custom extra metadata is preserved as-is, including explicit null values.
            data = document.metadata.model_dump()
            if data.get("summary") is None:
                data.pop("summary", None)
            yaml.dump(data, output)  # pyright: ignore[reportUnknownMemberType]
            return f"---\n{output.getvalue()}---\n{document.body}".encode()
        except (ValueError, YAMLError) as exc:
            raise InvalidDocumentError(path, exc) from exc

    def create[M: Metadata](self, path: str | PurePosixPath, document: Document[M]) -> None:
        relative = PathInput.model_validate({"path": path}).path
        content = self._encode(relative, document)
        target = self.root / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if self._case_conflict(target):
                message = f"{relative} differs only by case"
                raise FileExistsError(message)  # noqa: TRY301
            atomic_create(target, content)
        except FileExistsError as exc:
            raise DocumentExistsError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def _case_conflict(self, target: Path) -> bool:
        """Return whether a sibling shares target's name ignoring case."""
        folded = target.name.casefold()
        try:
            entries = list(target.parent.iterdir())
        except FileNotFoundError:
            return False
        return any(
            child.name != target.name and child.name.casefold() == folded for child in entries
        )

    def write[M: Metadata](self, path: str | PurePosixPath, document: Document[M]) -> None:
        relative = PathInput.model_validate({"path": path}).path
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

    def metadata(self, path: str | PurePosixPath) -> FileMetadata:
        relative = PathInput.model_validate({"path": path}).path
        try:
            info = (self.root / relative).stat()
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError("Expected a regular file or directory")  # noqa: TRY301
            return FileMetadata(
                path=relative,
                modified=datetime.fromtimestamp(info.st_mtime, UTC),
                kind="directory" if stat.S_ISDIR(info.st_mode) else "file",
            )
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except (OSError, ValueError) as exc:
            raise StorageError(relative, exc) from exc

    def _find_matching_files(self, scope: DocumentScope) -> list[FileMetadata]:
        try:
            directory = self.root / scope.path
            if not directory.exists():
                return []
            if not directory.is_dir():
                raise NotADirectoryError(str(directory))
            return [
                self.metadata(PurePosixPath(match.relative_to(self.root).as_posix()))
                for match in _glob_regular_files(
                    directory, [str(scope.pattern)], include_dotfiles=False
                )
            ]
        except OSError as exc:
            raise StorageError(scope.path, exc) from exc

    def get_last_activity_at(
        self, path: str | PurePosixPath, activity_scopes: tuple[DocumentScope, ...] = ()
    ) -> datetime:
        """Read activity timestamps without loading descendant documents."""
        record = self.metadata(path)
        last_activity_at = record.modified
        for scope in activity_scopes:
            for child in self._find_matching_files(
                DocumentScope(path=record.path.parent / scope.path, pattern=scope.pattern)
            ):
                last_activity_at = max(last_activity_at, child.modified)
        return last_activity_at

    def list[M: Metadata](
        self,
        collection: DocumentCollection,
        metadata_type: type[M],
        query: DocumentQuery | None = None,
    ) -> list[DocumentRecord[M]]:
        query = query or DocumentQuery()
        matching_documents: list[DocumentRecord[M]] = []
        for file_metadata in self._find_matching_files(collection):
            document = self.read(file_metadata.path, metadata_type)
            name = (
                file_metadata.path.parent.name
                if collection.name_source == "parent"
                else file_metadata.path.relative_to(collection.path).with_suffix("").as_posix()
            )
            last_activity_at = self.get_last_activity_at(
                file_metadata.path, collection.activity_scopes
            )
            if self._matches_query(document, last_activity_at, query):
                matching_documents.append(
                    DocumentRecord(
                        name=name,
                        path=file_metadata.path,
                        metadata=document.metadata,
                        last_activity_at=last_activity_at,
                        summary=document.get_or_derive_summary(),
                    )
                )
        matching_documents.sort(key=lambda record: record.name)
        # Stable sorting preserves ascending names for equal primary keys.
        if query.sort == "created":
            matching_documents.sort(
                key=lambda record: record.metadata.created, reverse=query.descending
            )
        elif query.sort == "updated":
            matching_documents.sort(
                key=lambda record: record.last_activity_at, reverse=query.descending
            )
        elif query.descending:
            matching_documents.reverse()
        return matching_documents if query.limit is None else matching_documents[: query.limit]

    @staticmethod
    def _matches_query[M: Metadata](
        document: Document[M], last_activity_at: datetime, query: DocumentQuery
    ) -> bool:
        metadata = document.metadata
        if query.tags is not None:
            document_tags = {tag.casefold() for tag in metadata.tags}
            if document_tags.isdisjoint(tag.casefold() for tag in query.tags):
                return False
        if isinstance(query, StatusQuery):
            statuses = cast("StatusQuery[str]", query).statuses
            if statuses is not None and (
                not isinstance(metadata, StatusMetadata)
                or cast("StatusMetadata[str]", metadata).status not in statuses
            ):
                return False
        for value, bounds in (
            (metadata.created, query.created_range),
            (last_activity_at, query.updated_range),
        ):
            if bounds is not None and (
                (bounds.gte is not None and value < bounds.gte)
                or (bounds.lte is not None and value > bounds.lte)
            ):
                return False
        return True


def _glob_regular_files(
    directory: Path, patterns: list[str], *, include_dotfiles: bool
) -> list[Path]:
    """Glob patterns under directory, keeping regular files inside the base directory."""
    files: list[Path] = []
    base = directory.resolve()
    for pattern in patterns:
        for match in directory.glob(pattern):
            try:
                match.resolve().relative_to(base)
                relative = match.relative_to(directory)
            except ValueError:
                continue
            if not include_dotfiles and any(part.startswith(".") for part in relative.parts):
                continue
            if match.is_file():
                files.append(match)
    return files
