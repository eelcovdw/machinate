from pathlib import PurePosixPath

from pydantic import ValidationError, validate_call

from machinate.models.batch import BatchCreateError, first_validation_message
from machinate.models.context import Context, ContextSummary, ContextUpdate
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentQuery,
    DocumentStore,
    Layout,
    PlanMetadata,
)
from machinate.storage.errors import MissingDocumentError, StorageError
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
        self.document_store.create(
            self.layout.context(plan, name), Document(metadata=metadata, body=body)
        )
        return self.get(plan, name)

    @validate_call
    def create_batch(
        self, plan: Name, names: list[str], metadata: ContextMetadata, body: str = ""
    ) -> tuple[list[Context], list[BatchCreateError]]:
        """Create many contexts: preflight conflicts, report per-name failures.

        Invalid and already-existing names become BatchCreateError entries;
        every remaining name is still attempted, so a mid-batch failure cannot
        silently skip later names.
        """
        self._require_plan(plan)
        errors: list[BatchCreateError] = []
        candidates: list[str] = []
        for name in names:
            try:
                valid = ContextNameInput(name=name).name
            except ValidationError as exc:
                errors.append(BatchCreateError(name=name, error=first_validation_message(exc)))
                continue
            try:
                self.document_store.metadata(self.layout.context(plan, valid))
            except MissingDocumentError:
                candidates.append(valid)
            except OSError as exc:
                errors.append(BatchCreateError(name=name, error=str(exc)))
            else:
                errors.append(
                    BatchCreateError(
                        name=valid, error=f"Already exists: {self.layout.context(plan, valid)}"
                    )
                )
        created: list[Context] = []
        for name in candidates:
            try:
                created.append(self.create(plan, name, metadata, body))
            except (StorageError, ValidationError, OSError) as exc:
                errors.append(BatchCreateError(name=name, error=str(exc)))
        return created, errors

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
            summary=context.document.get_or_derive_summary(),
            last_activity_at=context.modified_at,
        )

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        self._require_plan(plan)
        return self.layout.context_collection(plan).path

    @validate_call
    def update(self, plan: Name, name: ContextName, changes: ContextUpdate) -> Context:
        context = self.get(plan, name)
        if not changes.model_fields_set:
            return context
        document = context.document
        if "body" in changes.model_fields_set:
            document.body = changes.body
        if "summary" in changes.model_fields_set:
            document.metadata.summary = changes.summary or None
        if "tags" in changes.model_fields_set:
            document.metadata.tags = changes.tags if changes.tags is not None else []
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
                summary=record.summary,
                last_activity_at=record.last_activity_at,
            )
            for record in records
        ]
