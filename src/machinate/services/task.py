from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.task import Task, TaskSummary, TaskUpdate
from machinate.storage import Document, DocumentStore, Layout, PlanMetadata, TaskMetadata, TaskQuery
from machinate.storage.models import Name, TaskName, TaskStatus


class TaskService:
    def __init__(self, document_store: DocumentStore, layout: Layout) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout

    def _require_plan(self, plan: str) -> None:
        self.document_store.read(self.layout.plan(plan), PlanMetadata)

    @validate_call
    def create(self, plan: Name, name: TaskName, metadata: TaskMetadata, body: str = "") -> Task:
        self._require_plan(plan)
        self.document_store.create(
            self.layout.task(plan, name), Document(metadata=metadata, body=body)
        )
        return self.get(plan, name)

    @validate_call
    def get(self, plan: Name, name: TaskName) -> Task:
        self._require_plan(plan)
        path = self.layout.task(plan, name)
        return Task(
            name=name,
            path=path,
            document=self.document_store.read(path, TaskMetadata),
            modified_at=self.document_store.metadata(path).modified,
        )

    @validate_call
    def info(self, plan: Name, name: TaskName) -> TaskSummary:
        task = self.get(plan, name)
        return TaskSummary(
            name=task.name,
            path=task.path,
            metadata=task.document.metadata,
            summary=task.document.get_or_derive_summary(),
            last_activity_at=task.modified_at,
        )

    @validate_call
    def directory(self, plan: Name) -> PurePosixPath:
        self._require_plan(plan)
        return self.layout.task_collection(plan).path

    @validate_call
    def update(self, plan: Name, name: TaskName, changes: TaskUpdate) -> Task:
        task = self.get(plan, name)
        if not changes.model_fields_set:
            return task
        document = task.document
        if "status" in changes.model_fields_set:
            document.metadata.status = changes.status
        if "body" in changes.model_fields_set:
            document.body = changes.body
        if "summary" in changes.model_fields_set:
            document.metadata.summary = changes.summary or None
        if "tags" in changes.model_fields_set:
            document.metadata.tags = changes.tags if changes.tags is not None else []
        self.document_store.write(task.path, document)
        return self.get(plan, name)

    @validate_call
    def set_status(self, plan: Name, name: TaskName, status: TaskStatus) -> Task:
        return self.update(plan, name, TaskUpdate(status=status))

    @validate_call
    def list(self, plan: Name, query: TaskQuery | None = None) -> list[TaskSummary]:
        self._require_plan(plan)
        records = self.document_store.list(self.layout.task_collection(plan), TaskMetadata, query)
        return [
            TaskSummary(
                name=record.name,
                path=record.path,
                metadata=record.metadata,
                summary=record.summary,
                last_activity_at=record.last_activity_at,
            )
            for record in records
        ]
