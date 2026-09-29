"""Context documents: plan-scoped, no status, nested names."""

from datetime import UTC, datetime
from pathlib import PurePosixPath
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
from machinate.services.document import Collection, DocumentService, ensure_plan
from machinate.storage import DocumentStore, Layout


class ContextService(DocumentService[ContextMetadata]):
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        super().__init__(
            document_store,
            layout,
            Collection(
                kind="context",
                metadata_type=ContextMetadata,
                storage=lambda plan: layout.context_collection(ensure_plan(plan)),
                path=lambda plan, name: layout.context(ensure_plan(plan), name),
                requires_plan=True,
            ),
        )

    @override
    def _build_metadata(self, create: CreateInput) -> ContextMetadata:
        return ContextMetadata(
            created_at=datetime.now(UTC), summary=create.summary or None, tags=create.tags
        )

    @validate_call
    def create(
        self, plan: Name, name: NestedName, create: CreateInput
    ) -> LoadedDocument[ContextMetadata]:
        return self._create(plan, name, create)

    @validate_call
    def create_batch(
        self, plan: Name, names: list[str], create: CreateInput
    ) -> BatchCreated[LoadedDocument[ContextMetadata]]:
        return self._create_batch(plan, names, create)

    @validate_call
    def get(self, plan: Name, name: NestedName) -> LoadedDocument[ContextMetadata]:
        return self._get(plan, name)

    @validate_call
    def info(self, plan: Name, name: NestedName) -> DocumentRecord[ContextMetadata]:
        return self._info(plan, name)

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        return self._directory(plan)

    @validate_call
    def path(self, plan: Name, name: NestedName) -> PurePosixPath:
        return self._path(plan, name)

    @validate_call
    def update(
        self, plan: Name, name: NestedName, changes: DocumentUpdate
    ) -> LoadedDocument[ContextMetadata]:
        return self._update(plan, name, changes)

    @validate_call
    def list_records(
        self, plan: Name, query: DocumentQuery | None = None
    ) -> list[DocumentRecord[ContextMetadata]]:
        return self._list(plan, query)

    @validate_call
    def count_documents(self, plan: Name) -> int:
        """Count contexts by file discovery, without parsing them."""
        return self._count(plan)
