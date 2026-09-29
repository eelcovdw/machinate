from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.documents import (
    NESTED_NAME_ADAPTER,
    DocumentRecord,
    LoadedDocument,
    Name,
    NestedName,
    ParsedDocument,
    PlanMetadata,
    TaskMetadata,
    TaskStatus,
)
from machinate.models.operations import BatchCreated, StatusCreateInput, StatusUpdate, TaskQuery
from machinate.services.batch import create_documents
from machinate.storage import DocumentStore, Layout


class TaskService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    def _require_plan(self, plan: Name) -> None:
        self.document_store.read(self.layout.plan(plan), PlanMetadata)

    @staticmethod
    def _build_metadata(create: StatusCreateInput[TaskStatus]) -> TaskMetadata:
        return TaskMetadata(
            created_at=datetime.now(UTC),
            summary=create.summary,
            tags=create.tags,
            status=create.status if create.status is not None else "todo",
        )

    def _record(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[TaskMetadata]
    ) -> DocumentRecord[TaskMetadata]:
        """Build a task record, statting the file once."""
        return DocumentRecord[TaskMetadata].from_document(
            document,
            name=name,
            path=path,
            modified_at=self.document_store.metadata(path).modified_at,
        )

    def _loaded(
        self, path: PurePosixPath, name: NestedName, document: ParsedDocument[TaskMetadata]
    ) -> LoadedDocument[TaskMetadata]:
        return LoadedDocument(record=self._record(path, name, document), body=document.body)

    @validate_call
    def create(
        self, plan: Name, name: NestedName, create: StatusCreateInput[TaskStatus]
    ) -> LoadedDocument[TaskMetadata]:
        self._require_plan(plan)
        return self._create(plan, name, self._build_metadata(create))

    def _create(
        self, plan: Name, name: NestedName, metadata: TaskMetadata
    ) -> LoadedDocument[TaskMetadata]:
        """Write a task without re-checking the plan; callers must have required it."""
        path = self.layout.task(plan, name)
        document = ParsedDocument(metadata=metadata, body="")
        self.document_store.create(path, document)
        return self._loaded(path, name, document)

    @validate_call
    def create_batch(
        self, plan: Name, names: list[str], create: StatusCreateInput[TaskStatus]
    ) -> BatchCreated[LoadedDocument[TaskMetadata]]:
        """Create many tasks, reporting per-name failures instead of aborting the batch."""
        self._require_plan(plan)
        metadata = self._build_metadata(create)
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=NESTED_NAME_ADAPTER.validate_python,
            path_for=lambda name: self.layout.task(plan, name),
            create=lambda name: self._create(plan, name, metadata),
        )

    @validate_call
    def get(self, plan: Name, name: NestedName) -> LoadedDocument[TaskMetadata]:
        self._require_plan(plan)
        return self._get(plan, name)

    def _read(
        self, plan: Name, name: NestedName
    ) -> tuple[PurePosixPath, ParsedDocument[TaskMetadata]]:
        path = self.layout.task(plan, name)
        return path, self.document_store.read(path, TaskMetadata)

    def _get(self, plan: Name, name: NestedName) -> LoadedDocument[TaskMetadata]:
        path, document = self._read(plan, name)
        return self._loaded(path, name, document)

    @validate_call
    def info(self, plan: Name, name: NestedName) -> DocumentRecord[TaskMetadata]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        return self._record(path, name, document)

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        """Store-relative tasks directory; validates the plan exists without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        return self.layout.task_collection(plan).path

    @validate_call
    def path(self, plan: Name, name: NestedName) -> PurePosixPath:
        """Store-relative task path; validates plan and task exist without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        target = self.layout.task(plan, name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def update(
        self, plan: Name, name: NestedName, changes: StatusUpdate[TaskStatus]
    ) -> LoadedDocument[TaskMetadata]:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        updated = changes.apply_to(document)
        if updated is not None:
            self.document_store.write(path, updated)
            document = updated
        return self._loaded(path, name, document)

    @validate_call
    def list(
        self, plan: Name, query: TaskQuery | None = None
    ) -> list[DocumentRecord[TaskMetadata]]:
        self._require_plan(plan)
        return self.document_store.list(self.layout.task_collection(plan), TaskMetadata, query)
