from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.batch import BatchCreateError
from machinate.models.context import Context, ContextUpdate
from machinate.services.batch import create_documents
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentQuery,
    DocumentRecord,
    DocumentStore,
    Layout,
    PlanMetadata,
)
from machinate.storage.models import ContextName, ContextNameInput, Name


class ContextService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    def _require_plan(self, plan: str) -> None:
        self.document_store.read(self.layout.plan(plan), PlanMetadata)

    @validate_call
    def create(
        self, plan: Name, name: ContextName, metadata: ContextMetadata, body: str = ""
    ) -> Context:
        self._require_plan(plan)
        return self._create(plan, name, metadata, body)

    def _create(
        self, plan: Name, name: ContextName, metadata: ContextMetadata, body: str = ""
    ) -> Context:
        """Write a context without re-checking the plan; callers must have required it."""
        path = self.layout.context(plan, name)
        document = Document(metadata=metadata, body=body)
        self.document_store.create(path, document)
        return self._context(path, name, document)

    @validate_call
    def create_batch(
        self, plan: Name, names: list[str], metadata: ContextMetadata, body: str = ""
    ) -> tuple[list[Context], list[BatchCreateError]]:
        """Create many contexts, reporting per-name failures instead of aborting the batch."""
        self._require_plan(plan)
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=lambda name: ContextNameInput(name=name).name,
            path_for=lambda name: self.layout.context(plan, name),
            create=lambda name: self._create(plan, name, metadata, body),
        )

    @validate_call
    def get(self, plan: Name, name: ContextName) -> Context:
        self._require_plan(plan)
        return self._get(plan, name)

    def _read(
        self, plan: Name, name: ContextName
    ) -> tuple[PurePosixPath, Document[ContextMetadata]]:
        path = self.layout.context(plan, name)
        return path, self.document_store.read(path, ContextMetadata)

    def _context(
        self, path: PurePosixPath, name: ContextName, document: Document[ContextMetadata]
    ) -> Context:
        """Build a context from an already-loaded document, statting the file once."""
        return Context(
            name=name,
            path=path,
            document=document,
            modified_at=self.document_store.metadata(path).modified,
        )

    def _get(self, plan: Name, name: ContextName) -> Context:
        path, document = self._read(plan, name)
        return self._context(path, name, document)

    @validate_call
    def info(self, plan: Name, name: ContextName) -> DocumentRecord[ContextMetadata]:
        context = self.get(plan, name)
        return DocumentRecord[ContextMetadata].from_document(
            context.document,
            name=context.name,
            path=context.path,
            last_activity_at=context.modified_at,
        )

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        """Storage-relative context directory; validates the plan exists without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        return self.layout.context_collection(plan).path

    @validate_call
    def path(self, plan: Name, name: ContextName) -> PurePosixPath:
        """Storage-relative context path; validates plan and context exist without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        target = self.layout.context(plan, name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def update(self, plan: Name, name: ContextName, changes: ContextUpdate) -> Context:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        if changes.apply_to(document):
            self.document_store.write(path, document)
        return self._context(path, name, document)

    @validate_call
    def list(
        self, plan: Name, query: DocumentQuery | None = None
    ) -> list[DocumentRecord[ContextMetadata]]:
        self._require_plan(plan)
        return self.document_store.list(
            self.layout.context_collection(plan), ContextMetadata, query
        )
