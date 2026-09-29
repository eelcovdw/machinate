"""Generic document service shared by the plan, task, context, and doc resources.

The service owns every storage interaction (create, read, update, list, locate,
count); the resource services are thin subclasses that bind a :class:`Collection`
and expose the resource-shaped public methods.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from machinate.models.documents import (
    NESTED_NAME_ADAPTER,
    DocumentRecord,
    LoadedDocument,
    Metadata,
    Name,
    NestedName,
    ParsedDocument,
)
from machinate.models.operations import (
    BatchCreated,
    CreateInput,
    DocumentQuery,
)
from machinate.services.batch import create_documents
from machinate.storage import DocumentStore, Layout
from machinate.storage.models import DocumentCollection as StorageCollection


class DocumentChanges(Protocol):
    """An update that can be applied to a parsed document."""

    def apply_to[M: Metadata](self, document: ParsedDocument[M]) -> ParsedDocument[M] | None: ...


@dataclass(frozen=True, slots=True)
class Collection[M: Metadata]:
    """One kind of document: its metadata type and where its files live.

    ``storage`` and ``path`` take the owning plan name; plan and doc ignore it.
    ``requires_plan`` controls whether the owning plan must exist first.
    """

    metadata_type: type[M]
    storage: Callable[[Name | None], StorageCollection]
    path: Callable[[Name | None, NestedName], PurePosixPath]
    requires_plan: bool = True


def ensure_plan(plan: Name | None) -> Name:
    """Return the plan name, or fail when a project-level document kind received none."""
    if plan is None:
        msg = "A plan name is required for this document kind"
        raise ValueError(msg)
    return plan


class DocumentService[M: Metadata, C: CreateInput = CreateInput](ABC):
    """Create, read, update, list, locate, and count one kind of document.

    Subclasses bind a collection and build their metadata from the typed create input.
    """

    def __init__(
        self, document_store: DocumentStore, layout: Layout, collection: Collection[M]
    ) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout
        self.collection: Collection[M] = collection

    # --- paths and existence ------------------------------------------------

    def _require_plan(self, plan: Name | None) -> None:
        """The single plan-existence check; every resource uses this instead of parsing."""
        if not self.collection.requires_plan:
            return
        self.document_store.metadata(self.layout.plan(ensure_plan(plan)))

    def _directory(self, plan: Name | None) -> PurePosixPath:
        return self.collection.storage(plan).path

    def _path(self, plan: Name | None, name: NestedName) -> PurePosixPath:
        self._require_plan(plan)
        target = self.collection.path(plan, name)
        self.document_store.metadata(target)
        return target

    def _count(self, plan: Name | None) -> int:
        """Count documents by file discovery without parsing them."""
        return self.document_store.count_files(self.collection.storage(plan))

    # --- metadata and records ----------------------------------------------

    @abstractmethod
    def _build_metadata(self, create: C) -> M:
        """Build the full metadata a new document is stamped with."""

    def _record(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[M]
    ) -> DocumentRecord[M]:
        return DocumentRecord[M].from_document(
            document,
            name=name,
            path=path,
            modified_at=self.document_store.metadata(path).modified_at,
        )

    def _loaded(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[M]
    ) -> LoadedDocument[M]:
        return LoadedDocument(record=self._record(path, name, document), body=document.body)

    def _read(self, plan: Name | None, name: NestedName) -> tuple[PurePosixPath, ParsedDocument[M]]:
        path = self.collection.path(plan, name)
        return path, self.document_store.read(path, self.collection.metadata_type)

    # --- operations ---------------------------------------------------------

    def _write(self, plan: Name | None, name: NestedName, metadata: M) -> LoadedDocument[M]:
        path = self.collection.path(plan, name)
        document = ParsedDocument(metadata=metadata, body="")
        self.document_store.create(path, document)
        return self._loaded(path, name, document)

    def _create(self, plan: Name | None, name: NestedName, create: C) -> LoadedDocument[M]:
        self._require_plan(plan)
        return self._write(plan, name, self._build_metadata(create))

    def _create_batch(
        self, plan: Name | None, names: list[str], create: C
    ) -> BatchCreated[LoadedDocument[M]]:
        self._require_plan(plan)
        metadata = self._build_metadata(create)
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=NESTED_NAME_ADAPTER.validate_python,
            path_for=lambda name: self.collection.path(plan, name),
            create=lambda name: self._write(plan, name, metadata),
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
        self, plan: Name | None, name: NestedName, changes: DocumentChanges
    ) -> LoadedDocument[M]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        updated = changes.apply_to(document)
        if updated is not None:
            self.document_store.write(path, updated)
            document = updated
        return self._loaded(path, name, document)

    def _list(self, plan: Name | None, query: DocumentQuery | None) -> list[DocumentRecord[M]]:
        self._require_plan(plan)
        return self.document_store.list(
            self.collection.storage(plan), self.collection.metadata_type, query
        )
