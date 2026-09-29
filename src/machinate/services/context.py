from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.documents import (
    NESTED_NAME_ADAPTER,
    ContextMetadata,
    DocumentRecord,
    LoadedDocument,
    Name,
    NestedName,
    ParsedDocument,
    PlanMetadata,
)
from machinate.models.operations import BatchCreateError, ContextUpdate, CreateInput, DocumentQuery
from machinate.services.batch import create_documents
from machinate.storage import DocumentStore, Layout


class ContextService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    def _require_plan(self, plan: Name) -> None:
        self.document_store.read(self.layout.plan(plan), PlanMetadata)

    @staticmethod
    def _build_metadata(create: CreateInput) -> ContextMetadata:
        return ContextMetadata(
            created_at=datetime.now(UTC), summary=create.summary, tags=create.tags
        )

    def _record(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[ContextMetadata]
    ) -> DocumentRecord[ContextMetadata]:
        """Build a context record, statting the file once."""
        return DocumentRecord[ContextMetadata].from_document(
            document,
            name=name,
            path=path,
            modified_at=self.document_store.metadata(path).modified_at,
        )

    def _loaded(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[ContextMetadata]
    ) -> LoadedDocument[ContextMetadata]:
        return LoadedDocument(record=self._record(path, name, document), body=document.body)

    @validate_call
    def create(
        self, plan: Name, name: NestedName, create: CreateInput, body: str = ""
    ) -> LoadedDocument[ContextMetadata]:
        self._require_plan(plan)
        return self._create(plan, name, self._build_metadata(create), body)

    def _create(
        self, plan: Name, name: NestedName, metadata: ContextMetadata, body: str = ""
    ) -> LoadedDocument[ContextMetadata]:
        """Write a context without re-checking the plan; callers must have required it."""
        path = self.layout.context(plan, name)
        document = ParsedDocument(metadata=metadata, body=body)
        self.document_store.create(path, document)
        return self._loaded(path, name, document)

    @validate_call
    def create_batch(
        self, plan: Name, names: list[str], create: CreateInput, body: str = ""
    ) -> tuple[list[LoadedDocument[ContextMetadata]], list[BatchCreateError]]:
        """Create many contexts, reporting per-name failures instead of aborting the batch."""
        self._require_plan(plan)
        metadata = self._build_metadata(create)
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=NESTED_NAME_ADAPTER.validate_python,
            path_for=lambda name: self.layout.context(plan, name),
            create=lambda name: self._create(plan, name, metadata, body),
        )

    @validate_call
    def get(self, plan: Name, name: NestedName) -> LoadedDocument[ContextMetadata]:
        self._require_plan(plan)
        return self._get(plan, name)

    def _read(
        self, plan: Name, name: NestedName
    ) -> tuple[PurePosixPath, ParsedDocument[ContextMetadata]]:
        path = self.layout.context(plan, name)
        return path, self.document_store.read(path, ContextMetadata)

    def _get(self, plan: Name, name: NestedName) -> LoadedDocument[ContextMetadata]:
        path, document = self._read(plan, name)
        return self._loaded(path, name, document)

    @validate_call
    def info(self, plan: Name, name: NestedName) -> DocumentRecord[ContextMetadata]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        return self._record(path, name, document)

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        """Store-relative context directory; validates the plan exists without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        return self.layout.context_collection(plan).path

    @validate_call
    def path(self, plan: Name, name: NestedName) -> PurePosixPath:
        """Store-relative context path; validates plan and context exist without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        target = self.layout.context(plan, name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def update(
        self, plan: Name, name: NestedName, changes: ContextUpdate
    ) -> LoadedDocument[ContextMetadata]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        if changes.apply_to(document):
            self.document_store.write(path, document)
        return self._loaded(path, name, document)

    @validate_call
    def list(
        self, plan: Name, query: DocumentQuery | None = None
    ) -> list[DocumentRecord[ContextMetadata]]:
        self._require_plan(plan)
        return self.document_store.list(
            self.layout.context_collection(plan), ContextMetadata, query
        )
