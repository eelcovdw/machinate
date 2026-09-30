"""Context documents: plan-scoped, no status, nested names."""

from datetime import UTC, datetime
from typing import override

from pydantic import validate_call

from machinate.models.documents import (
    ContextMetadata,
    DocumentRecord,
    LoadedDocument,
    Name,
    NestedName,
)
from machinate.models.operations import (
    BatchCreated,
    CreateInput,
    DocumentQuery,
    DocumentUpdate,
)
from machinate.services.document import Collection, DocumentService, LocatedPath, ensure_plan
from machinate.storage.document_store import DocumentStore
from machinate.storage.layout import Layout


class ContextService(DocumentService[ContextMetadata]):
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        super().__init__(
            document_store,
            layout,
            Collection(
                kind="context",
                metadata_type=ContextMetadata,
                collection=lambda plan: layout.context_collection(ensure_plan(plan)),
                path=lambda plan, name: layout.context_path(ensure_plan(plan), name),
                requires_plan=True,
                directory_kind="context_directory",
            ),
        )

    @override
    def _build_metadata(self, create: CreateInput) -> ContextMetadata:
        return ContextMetadata(
            created_at=datetime.now(UTC), summary=create.summary or None, tags=create.tags
        )

    @validate_call
    def create_many(
        self, plan: Name, names: list[str], create: CreateInput
    ) -> BatchCreated[DocumentRecord[ContextMetadata]]:
        return self._create_many(plan, names, create)

    @validate_call
    def get(self, plan: Name, name: NestedName) -> LoadedDocument[ContextMetadata]:
        return self._get(plan, name)

    @validate_call
    def get_record(self, plan: Name, name: NestedName) -> DocumentRecord[ContextMetadata]:
        return self._info(plan, name)

    @validate_call
    def locate(self, plan: Name, name: NestedName | None = None) -> LocatedPath:
        return self._locate(plan, name)

    @validate_call
    def update(
        self, plan: Name, name: NestedName, update: DocumentUpdate
    ) -> LoadedDocument[ContextMetadata]:
        return self._update(plan, name, update)

    @validate_call
    def list_records(
        self, plan: Name, query: DocumentQuery | None = None
    ) -> list[DocumentRecord[ContextMetadata]]:
        return self._list(plan, query)

    @validate_call
    def count_documents(self, plan: Name) -> int:
        """Count contexts by file discovery, without parsing them."""
        return self._count(plan)
