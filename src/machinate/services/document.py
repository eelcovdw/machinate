"""Generic document service shared by the plan, task, context, and doc resources.

The service owns every storage interaction (create, read, update, list, locate,
count); the resource services are thin subclasses that bind a :class:`Collection`
and expose the resource-shaped public methods.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from machinate.models.documents import (
    NESTED_NAME_ADAPTER,
    CollectionKind,
    DocumentRecord,
    LoadedDocument,
    Metadata,
    Name,
    NestedName,
    ParsedDocument,
    PathKind,
)
from machinate.models.operations import (
    BatchCreated,
    CreateInput,
    DocumentQuery,
)
from machinate.services.batch import create_many
from machinate.services.errors import (
    ExistsError,
    InputError,
    InvalidDocumentError,
    NotFoundError,
    invalid_document_detail,
)
from machinate.storage import DocumentStore, Layout
from machinate.storage.errors import (
    DocumentExistsError,
    MissingDocumentError,
)
from machinate.storage.errors import (
    InvalidDocumentError as StorageInvalidDocumentError,
)
from machinate.storage.models import DocumentCollection as StorageCollection


class DocumentChanges(Protocol):
    """An update that can be applied to a parsed document."""

    def apply_to[M: Metadata](self, document: ParsedDocument[M]) -> ParsedDocument[M] | None: ...


@dataclass(frozen=True, slots=True)
class Collection[M: Metadata]:
    """One kind of document: its metadata type and where its files live.

    ``path`` and ``collection`` take the owning plan name; plan and doc ignore it.
    ``requires_plan`` controls whether the owning plan must exist first. ``kind`` is
    the singular noun used in domain errors (``not found``, ``already exists``);
    ``directory_kind`` names the collection directory, or is ``None`` when the kind has
    no directory command (plans).
    """

    kind: CollectionKind
    metadata_type: type[M]
    collection: Callable[[Name | None], StorageCollection]
    path: Callable[[Name | None, NestedName], PurePosixPath]
    requires_plan: bool = True
    directory_kind: PathKind | None = None


@dataclass(frozen=True, slots=True)
class LocatedPath:
    """An absolute editing path, its kind, and whether it currently exists."""

    path: Path
    kind: PathKind
    # None for documents, whose existence is implied by the kind; directories report it.
    exists: bool | None


def ensure_plan(plan: Name | None) -> Name:
    """Return the plan name, or fail when a project-level document kind received none."""
    if plan is None:
        msg = "A plan name is required for this document kind"
        raise InputError(msg)
    return plan


@contextmanager
def _translate_errors(kind: str, name: str) -> Iterator[None]:
    """Turn storage failures into domain errors; the CLI renders both in one place."""
    try:
        yield
    except MissingDocumentError as exc:
        raise NotFoundError(kind, name) from exc
    except DocumentExistsError as exc:
        raise ExistsError(kind, name) from exc
    except StorageInvalidDocumentError as exc:
        raise InvalidDocumentError(str(exc.path), invalid_document_detail(exc.reason)) from exc


class DocumentService[M: Metadata, C: CreateInput = CreateInput](ABC):
    """Create, read, update, list, locate, and count one kind of document.

    Subclasses bind a collection and build their metadata from the typed create input.
    """

    def __init__(
        self, document_store: DocumentStore, layout: Layout, resource: Collection[M]
    ) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout
        self.resource: Collection[M] = resource

    # --- paths and existence ------------------------------------------------

    def require_plan(self, plan: Name | None) -> None:
        """Stat the owning plan document; every resource uses this plan-existence check."""
        plan_name = ensure_plan(plan)
        with _translate_errors("plan", plan_name):
            self.document_store.stat(self.layout.plan_path(plan_name))

    def _require_plan(self, plan: Name | None) -> None:
        if self.resource.requires_plan:
            self.require_plan(plan)

    def _locate(self, plan: Name | None, name: NestedName | None) -> LocatedPath:
        """Resolve a document or collection directory to an absolute path and its state."""
        self._require_plan(plan)
        if name is None:
            directory_kind = self.resource.directory_kind
            if directory_kind is None:
                msg = f"{self.resource.kind} has no collection directory"
                raise InputError(msg)
            relative = self.resource.collection(plan).path
            return LocatedPath(
                path=self.document_store.absolute_path(relative),
                kind=directory_kind,
                exists=self.document_store.is_directory(relative),
            )
        relative = self._path(plan, name)
        return LocatedPath(
            path=self.document_store.absolute_path(relative),
            kind=self.resource.kind,
            exists=None,
        )

    def _path(self, plan: Name | None, name: NestedName) -> PurePosixPath:
        self._require_plan(plan)
        target = self.resource.path(plan, name)
        with _translate_errors(self.resource.kind, name):
            self.document_store.stat(target)
        return target

    def _count(self, plan: Name | None) -> int:
        """Count documents by file discovery without parsing them."""
        return self.document_store.count_documents(self.resource.collection(plan))

    # --- metadata and records ----------------------------------------------

    @abstractmethod
    def _build_metadata(self, create: C) -> M:
        """Build the full metadata a new document is stamped with."""

    def _record(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[M]
    ) -> DocumentRecord[M]:
        with _translate_errors(self.resource.kind, name):
            modified_at = self.document_store.stat(path).modified_at
        return DocumentRecord[M].from_document(
            document, name=name, path=path, modified_at=modified_at
        )

    def _loaded(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[M]
    ) -> LoadedDocument[M]:
        return LoadedDocument(record=self._record(path, name, document), body=document.body)

    def _read(self, plan: Name | None, name: NestedName) -> tuple[PurePosixPath, ParsedDocument[M]]:
        path = self.resource.path(plan, name)
        with _translate_errors(self.resource.kind, name):
            document = self.document_store.read(path, self.resource.metadata_type)
        return path, document

    # --- operations ---------------------------------------------------------

    def _create_document(
        self, plan: Name | None, name: NestedName, metadata: M
    ) -> LoadedDocument[M]:
        path = self.resource.path(plan, name)
        document = ParsedDocument(metadata=metadata, body="")
        with _translate_errors(self.resource.kind, name):
            self.document_store.create(path, document)
        return self._loaded(path, name, document)

    def _create(self, plan: Name | None, name: NestedName, create: C) -> LoadedDocument[M]:
        self._require_plan(plan)
        return self._create_document(plan, name, self._build_metadata(create))

    def _create_many(
        self, plan: Name | None, names: list[str], create: C
    ) -> BatchCreated[LoadedDocument[M]]:
        self._require_plan(plan)
        metadata = self._build_metadata(create)
        return create_many(
            names=names,
            document_store=self.document_store,
            validate_name=NESTED_NAME_ADAPTER.validate_python,
            path_for=lambda name: self.resource.path(plan, name),
            create=lambda name: self._create_document(plan, name, metadata),
        )

    def _get(self, plan: Name | None, name: NestedName) -> LoadedDocument[M]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        return self._loaded(path, name, document)

    def _info(self, plan: Name | None, name: NestedName) -> DocumentRecord[M]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        return self._record(path, name, document)

    def _update(
        self, plan: Name | None, name: NestedName, update: DocumentChanges
    ) -> LoadedDocument[M]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        updated = update.apply_to(document)
        if updated is not None:
            with _translate_errors(self.resource.kind, name):
                self.document_store.write(path, updated)
            document = updated
        return self._loaded(path, name, document)

    def _list(self, plan: Name | None, query: DocumentQuery | None) -> list[DocumentRecord[M]]:
        self._require_plan(plan)
        collection = self.resource.collection(plan)
        with _translate_errors(self.resource.kind, collection.path.as_posix()):
            records = self.document_store.list(collection, self.resource.metadata_type, query)
        return _sort_records(records, query or DocumentQuery())


def _sort_records[M: Metadata](
    records: list[DocumentRecord[M]], query: DocumentQuery
) -> list[DocumentRecord[M]]:
    """Order and limit records by the query's stored sort key."""
    records.sort(key=lambda record: record.name)
    # Stable sorting preserves ascending names for equal primary keys.
    if query.sort == "created_at":
        records.sort(key=lambda record: record.metadata.created_at, reverse=query.descending)
    elif query.sort == "modified_at":
        records.sort(key=lambda record: record.modified_at, reverse=query.descending)
    elif query.descending:
        records.reverse()
    return records if query.limit is None else records[: query.limit]
