import stat
import sys
import tempfile
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path, PurePosixPath
from typing import cast

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from upath import UPath

from .errors import DocumentExistsError, InvalidDocumentError, MissingDocumentError, StorageError
from .models import Document, FileMetadata, Metadata, PathInput, StatusMetadata
from .queries import DocumentCollection, DocumentQuery, DocumentRecord, DocumentScope, StatusQuery


class DocumentStore:
    def __init__(self, root: UPath) -> None:
        if root.protocol not in {"", "file", "local"}:
            raise ValueError("DocumentStore currently supports local roots only")
        self.root: UPath = root

    def read[M: Metadata](self, path: str | PurePosixPath, metadata_type: type[M]) -> Document[M]:
        relative = PathInput.model_validate({"path": path}).path
        try:
            # Decode bytes directly so universal-newline translation cannot alter the body.
            text = (self.root / relative).read_bytes().decode("utf-8")
            lines = text.splitlines(keepends=True)
            if not lines or lines[0].rstrip("\r\n") != "---":
                raise ValueError("Missing YAML frontmatter")  # noqa: TRY301
            end = next((i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == "---"), None)
            if end is None:
                raise ValueError("Unterminated YAML frontmatter")  # noqa: TRY301
            data: object = YAML(typ="safe").load("".join(lines[1:end]))  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            return Document[metadata_type](
                metadata=metadata_type.model_validate(data), body="".join(lines[end + 1 :])
            )
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except (ValueError, YAMLError) as exc:
            raise InvalidDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def _encode[M: Metadata](self, path: PurePosixPath, document: Document[M]) -> bytes:
        try:
            output = StringIO()
            yaml = YAML(typ="safe")
            yaml.default_flow_style = False
            yaml.dump(document.metadata.model_dump(), output)  # pyright: ignore[reportUnknownMemberType]
            return f"---\n{output.getvalue()}---\n{document.body}".encode()
        except (ValueError, YAMLError) as exc:
            raise InvalidDocumentError(path, exc) from exc

    def create[M: Metadata](self, path: str | PurePosixPath, document: Document[M]) -> None:
        relative = PathInput.model_validate({"path": path}).path
        content = self._encode(relative, document)
        target = self.root / relative
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(content)
        except FileExistsError as exc:
            raise DocumentExistsError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def write[M: Metadata](self, path: str | PurePosixPath, document: Document[M]) -> None:
        relative = PathInput.model_validate({"path": path}).path
        content = self._encode(relative, document)
        target = self.root / relative
        temporary: Path | None = None
        try:
            info = target.stat()  # Updates must not silently create missing documents.
            if not stat.S_ISREG(info.st_mode):
                raise IsADirectoryError(str(target))
            # A sibling temporary file keeps replacement on the same filesystem.
            with tempfile.NamedTemporaryFile(dir=target.parent.path, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            temporary.chmod(stat.S_IMODE(info.st_mode))
            temporary.replace(target.path)
            temporary = None  # Replacement consumed the temporary file.
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc
        finally:
            if temporary is not None:
                failure = sys.exception()
                try:
                    temporary.unlink(missing_ok=True)
                except OSError as exc:
                    if failure is None:
                        raise StorageError(relative, exc) from exc
                    # Keep the write failure primary, but report the leftover temporary file.
                    failure.add_note(f"Could not remove temporary file {temporary}: {exc}")

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

    def discover(self, path: str | PurePosixPath = ".") -> list[FileMetadata]:
        """List immediate children in path order; a missing directory is an error."""
        relative = PathInput.model_validate({"path": path}).path
        try:
            children = sorted((self.root / relative).iterdir(), key=lambda child: child.name)
            return [self.metadata(relative / child.name) for child in children]
        except FileNotFoundError as exc:
            raise MissingDocumentError(relative, exc) from exc
        except OSError as exc:
            raise StorageError(relative, exc) from exc

    def _find_matching_files(self, scope: DocumentScope) -> list[FileMetadata]:
        try:
            directory = self.root / scope.path
            if not directory.exists():
                return []
            if not directory.is_dir():
                raise NotADirectoryError(str(directory))
            records = [
                self.metadata(PurePosixPath(child.relative_to(self.root).as_posix()))
                for child in directory.glob(str(scope.pattern))
            ]
            return [record for record in records if record.kind == "file"]
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
            if self._matches_query(name, document, last_activity_at, query):
                matching_documents.append(
                    DocumentRecord(
                        name=name,
                        path=file_metadata.path,
                        metadata=document.metadata,
                        last_activity_at=last_activity_at,
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
        name: str, document: Document[M], last_activity_at: datetime, query: DocumentQuery
    ) -> bool:
        metadata = document.metadata
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
        if query.search:
            values = [name, metadata.summary or ""]
            if query.search_body:
                values.append(document.body)
            return any(query.search.casefold() in value.casefold() for value in values)
        return True
