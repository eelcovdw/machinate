"""Project-wide doc documents: not plan-scoped, no status, nested names."""

from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import override

from pydantic import validate_call

from machinate.models.documents import (
    DocMetadata,
    DocumentRecord,
    LoadedDocument,
    NestedName,
)
from machinate.models.operations import (
    BatchCreated,
    CreateInput,
    DocumentQuery,
    DocumentUpdate,
)
from machinate.services.document import Collection, DocumentService, LocatedPath
from machinate.storage import DocumentStore, Layout


class DocService(DocumentService[DocMetadata]):
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        super().__init__(
            document_store,
            layout,
            Collection(
                kind="doc",
                metadata_type=DocMetadata,
                storage=lambda _plan: layout.docs_collection(),
                path=lambda _plan, name: layout.doc(name),
                requires_plan=False,
                directory_kind="docs_directory",
            ),
        )

    @override
    def _build_metadata(self, create: CreateInput) -> DocMetadata:
        return DocMetadata(
            created_at=datetime.now(UTC), summary=create.summary or None, tags=create.tags
        )

    @validate_call
    def create(self, name: NestedName, create: CreateInput) -> LoadedDocument[DocMetadata]:
        return self._create(None, name, create)

    @validate_call
    def create_batch(
        self, names: list[str], create: CreateInput
    ) -> BatchCreated[LoadedDocument[DocMetadata]]:
        return self._create_batch(None, names, create)

    @validate_call
    def get(self, name: NestedName) -> LoadedDocument[DocMetadata]:
        return self._get(None, name)

    @validate_call
    def info(self, name: NestedName) -> DocumentRecord[DocMetadata]:
        return self._info(None, name)

    @validate_call
    def directory(self) -> PurePosixPath:
        return self._directory(None)

    @validate_call
    def path(self, name: NestedName) -> PurePosixPath:
        return self._path(None, name)

    @validate_call
    def locate(self, name: NestedName | None = None) -> LocatedPath:
        return self._locate(None, name)

    @validate_call
    def update(self, name: NestedName, changes: DocumentUpdate) -> LoadedDocument[DocMetadata]:
        return self._update(None, name, changes)

    @validate_call
    def list_records(self, query: DocumentQuery | None = None) -> list[DocumentRecord[DocMetadata]]:
        return self._list(None, query)

    @validate_call
    def count_documents(self) -> int:
        """Count docs by file discovery, without parsing them."""
        return self._count(None)
