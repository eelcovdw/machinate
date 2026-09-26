from pydantic import validate_call

from machinate.models.context import Context, ContextSummary, ContextUpdate
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentQuery,
    DocumentStore,
    Layout,
    PlanMetadata,
)
from machinate.storage.models import ContextName, Name


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
        self.document_store.create(
            self.layout.context(plan, name), Document(metadata=metadata, body=body)
        )
        return self.get(plan, name)

    @validate_call
    def get(self, plan: Name, name: ContextName) -> Context:
        self._require_plan(plan)
        path = self.layout.context(plan, name)
        return Context(
            name=name,
            path=path,
            document=self.document_store.read(path, ContextMetadata),
            modified_at=self.document_store.metadata(path).modified,
        )

    @validate_call
    def info(self, plan: Name, name: ContextName) -> ContextSummary:
        context = self.get(plan, name)
        return ContextSummary(
            name=context.name,
            path=context.path,
            metadata=context.document.metadata,
            last_activity_at=context.modified_at,
        )

    @validate_call
    def update(self, plan: Name, name: ContextName, changes: ContextUpdate) -> Context:
        context = self.get(plan, name)
        if not changes.model_fields_set:
            return context
        document = context.document
        if "summary" in changes.model_fields_set:
            document.metadata.summary = changes.summary
        if "body" in changes.model_fields_set:
            document.body = changes.body
        self.document_store.write(context.path, document)
        return self.get(plan, name)

    @validate_call
    def list(self, plan: Name, query: DocumentQuery | None = None) -> list[ContextSummary]:
        self._require_plan(plan)
        records = self.document_store.list(
            self.layout.context_collection(plan), ContextMetadata, query
        )
        return [
            ContextSummary(
                name=record.name,
                path=record.path,
                metadata=record.metadata,
                last_activity_at=record.last_activity_at,
            )
            for record in records
        ]
