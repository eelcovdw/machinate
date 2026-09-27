from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.batch import BatchCreateError
from machinate.models.task import Task, TaskUpdate
from machinate.services.batch import create_documents
from machinate.storage import (
    Document,
    DocumentRecord,
    DocumentStore,
    Layout,
    PlanMetadata,
    TaskMetadata,
    TaskQuery,
)
from machinate.storage.models import Name, TaskName, TaskNameInput


class TaskService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    def _require_plan(self, plan: str) -> None:
        self.document_store.read(self.layout.plan(plan), PlanMetadata)

    @validate_call
    def create(self, plan: Name, name: TaskName, metadata: TaskMetadata, body: str = "") -> Task:
        self._require_plan(plan)
        return self._create(plan, name, metadata, body)

    def _create(self, plan: Name, name: TaskName, metadata: TaskMetadata, body: str = "") -> Task:
        """Write a task without re-checking the plan; callers must have required it."""
        path = self.layout.task(plan, name)
        document = Document(metadata=metadata, body=body)
        self.document_store.create(path, document)
        return self._task(path, name, document)

    @validate_call
    def create_batch(
        self, plan: Name, names: list[str], metadata: TaskMetadata, body: str = ""
    ) -> tuple[list[Task], list[BatchCreateError]]:
        """Create many tasks, reporting per-name failures instead of aborting the batch."""
        self._require_plan(plan)
        return create_documents(
            names=names,
            document_store=self.document_store,
            validate_name=lambda name: TaskNameInput(name=name).name,
            path_for=lambda name: self.layout.task(plan, name),
            create=lambda name: self._create(plan, name, metadata, body),
        )

    @validate_call
    def get(self, plan: Name, name: TaskName) -> Task:
        self._require_plan(plan)
        return self._get(plan, name)

    def _read(self, plan: Name, name: TaskName) -> tuple[PurePosixPath, Document[TaskMetadata]]:
        path = self.layout.task(plan, name)
        return path, self.document_store.read(path, TaskMetadata)

    def _task(self, path: PurePosixPath, name: TaskName, document: Document[TaskMetadata]) -> Task:
        """Build a task from an already-loaded document, statting the file once."""
        return Task(
            name=name,
            path=path,
            document=document,
            modified_at=self.document_store.metadata(path).modified,
        )

    def _get(self, plan: Name, name: TaskName) -> Task:
        path, document = self._read(plan, name)
        return self._task(path, name, document)

    @validate_call
    def info(self, plan: Name, name: TaskName) -> DocumentRecord[TaskMetadata]:
        task = self.get(plan, name)
        return DocumentRecord[TaskMetadata].from_document(
            task.document, name=task.name, path=task.path, last_activity_at=task.modified_at
        )

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        """Storage-relative tasks directory; validates the plan exists without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        return self.layout.task_collection(plan).path

    @validate_call
    def path(self, plan: Name, name: TaskName) -> PurePosixPath:
        """Storage-relative task path; validates plan and task exist without parsing."""
        self.document_store.metadata(self.layout.plan(plan))
        target = self.layout.task(plan, name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def update(self, plan: Name, name: TaskName, changes: TaskUpdate) -> Task:
        self._require_plan(plan)
        path, document = self._read(plan, name)
        changed = changes.apply_to(document)
        if "status" in changes.model_fields_set:
            document.metadata.status = changes.status
            changed = True
        if changed:
            self.document_store.write(path, document)
        return self._task(path, name, document)

    @validate_call
    def list(
        self, plan: Name, query: TaskQuery | None = None
    ) -> list[DocumentRecord[TaskMetadata]]:
        self._require_plan(plan)
        return self.document_store.list(self.layout.task_collection(plan), TaskMetadata, query)
