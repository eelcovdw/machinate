"""Task documents: plan-scoped, status-bearing, nested names."""

from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import override

from pydantic import validate_call

from machinate.models.documents import (
    DocumentRecord,
    LoadedDocument,
    Name,
    NestedName,
    TaskMetadata,
    TaskStatus,
)
from machinate.models.operations import (
    BatchCreated,
    StatusCreateInput,
    StatusUpdate,
    TaskQuery,
)
from machinate.services.document import Collection, DocumentService, ensure_plan
from machinate.storage import DocumentStore, Layout


class TaskService(DocumentService[TaskMetadata, StatusCreateInput[TaskStatus]]):
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        super().__init__(
            document_store,
            layout,
            Collection(
                metadata_type=TaskMetadata,
                storage=lambda plan: layout.task_collection(ensure_plan(plan)),
                path=lambda plan, name: layout.task(ensure_plan(plan), name),
                requires_plan=True,
            ),
        )

    @override
    def _build_metadata(self, create: StatusCreateInput[TaskStatus]) -> TaskMetadata:
        return TaskMetadata(
            created_at=datetime.now(UTC),
            summary=create.summary or None,
            tags=create.tags,
            status=create.status or "todo",
        )

    @validate_call
    def create(
        self, plan: Name, name: NestedName, create: StatusCreateInput[TaskStatus]
    ) -> LoadedDocument[TaskMetadata]:
        return self._create(plan, name, create)

    @validate_call
    def create_batch(
        self, plan: Name, names: list[str], create: StatusCreateInput[TaskStatus]
    ) -> BatchCreated[LoadedDocument[TaskMetadata]]:
        return self._create_batch(plan, names, create)

    @validate_call
    def get(self, plan: Name, name: NestedName) -> LoadedDocument[TaskMetadata]:
        return self._get(plan, name)

    @validate_call
    def info(self, plan: Name, name: NestedName) -> DocumentRecord[TaskMetadata]:
        return self._info(plan, name)

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        return self._directory(plan)

    @validate_call
    def path(self, plan: Name, name: NestedName) -> PurePosixPath:
        return self._path(plan, name)

    @validate_call
    def update(
        self, plan: Name, name: NestedName, changes: StatusUpdate[TaskStatus]
    ) -> LoadedDocument[TaskMetadata]:
        return self._update(plan, name, changes)

    @validate_call
    def list_records(
        self, plan: Name, query: TaskQuery | None = None
    ) -> list[DocumentRecord[TaskMetadata]]:
        return self._list(plan, query)
