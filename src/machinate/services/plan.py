from pydantic import validate_call

from machinate.models.plan import Plan, PlanInfo, PlanSummary, PlanUpdate
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentStore,
    Layout,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
    TaskMetadata,
)
from machinate.storage.models import Name, PlanStatus, TaskStatus
from machinate.storage.queries import PlanQuery


class PlanService:
    def __init__(
        self, document_store: DocumentStore, layout: Layout, project_state_store: ProjectStateStore
    ) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout
        self.project_state_store: ProjectStateStore = project_state_store

    @validate_call
    def create(self, name: Name, metadata: PlanMetadata, body: str = "") -> Plan:
        self.document_store.create(self.layout.plan(name), Document(metadata=metadata, body=body))
        return self.get(name)

    @validate_call
    def get(self, name: Name) -> Plan:
        path = self.layout.plan(name)
        return Plan(
            name=name,
            path=path,
            document=self.document_store.read(path, PlanMetadata),
            modified_at=self.document_store.metadata(path).modified,
        )

    @validate_call
    def update(self, name: Name, changes: PlanUpdate) -> Plan:
        plan = self.get(name)
        if not changes.model_fields_set:
            return plan
        document = plan.document
        if "summary" in changes.model_fields_set:
            document.metadata.summary = changes.summary
        if "status" in changes.model_fields_set:
            document.metadata.status = changes.status
        if "body" in changes.model_fields_set:
            document.body = changes.body
        self.document_store.write(plan.path, document)
        return self.get(name)

    @validate_call
    def set_status(self, name: Name, status: PlanStatus) -> Plan:
        return self.update(name, PlanUpdate(status=status))

    @validate_call
    def list(self, query: PlanQuery | None = None) -> list[PlanSummary]:
        plan_records = self.document_store.list(self.layout.plan_collection(), PlanMetadata, query)
        return [
            PlanSummary(
                name=record.name,
                path=record.path,
                metadata=record.metadata,
                last_activity_at=record.last_activity_at,
            )
            for record in plan_records
        ]

    @validate_call
    def set_current(self, name: Name) -> ProjectState:
        self.get(name)
        state = self.project_state_store.read()
        state.current_plan = name
        self.project_state_store.write(state)
        return state

    def get_current(self) -> Plan | None:
        name = self.project_state_store.read().current_plan
        return None if name is None else self.get(name)

    @validate_call
    def info(self, name: Name) -> PlanInfo:
        plan = self.get(name)
        task_records = self.document_store.list(self.layout.task_collection(name), TaskMetadata)
        context_records = self.document_store.list(
            self.layout.context_collection(name), ContextMetadata
        )
        task_counts: dict[TaskStatus, int] = {"todo": 0, "in-progress": 0, "done": 0}
        for task in task_records:
            task_counts[task.metadata.status] += 1
        return PlanInfo(
            plan=PlanSummary(
                name=plan.name,
                path=plan.path,
                metadata=plan.document.metadata,
                last_activity_at=self.document_store.get_last_activity_at(
                    plan.path, self.layout.plan_activity_scopes()
                ),
            ),
            task_counts=task_counts,
            context_count=len(context_records),
        )
