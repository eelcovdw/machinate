from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.plan import (
    Plan,
    PlanInfo,
    PlanOverview,
    PlanUpdate,
    ProjectOverview,
)
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentRecord,
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
    def path(self, name: Name) -> PurePosixPath:
        """Storage-relative plan path; validates the plan exists without parsing."""
        target = self.layout.plan(name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def get(self, name: Name) -> Plan:
        path = self.layout.plan(name)
        return self._plan(path, name, self.document_store.read(path, PlanMetadata))

    def _plan(self, path: PurePosixPath, name: Name, document: Document[PlanMetadata]) -> Plan:
        """Build a plan from an already-loaded document, statting the file once."""
        return Plan(
            name=name,
            path=path,
            document=document,
            modified_at=self.document_store.metadata(path).modified,
        )

    @validate_call
    def update(self, name: Name, changes: PlanUpdate) -> Plan:
        path = self.layout.plan(name)
        document = self.document_store.read(path, PlanMetadata)
        changed = changes.apply_to(document)
        if "status" in changes.model_fields_set:
            document.metadata.status = changes.status
            changed = True
        if changed:
            self.document_store.write(path, document)
        return self._plan(path, name, document)

    @validate_call
    def list(self, query: PlanQuery | None = None) -> list[DocumentRecord[PlanMetadata]]:
        return self.document_store.list(self.layout.plan_collection(), PlanMetadata, query)

    @validate_call
    def set_current(self, name: Name) -> ProjectState:
        self.get(name)
        state = self.project_state_store.read()
        state.current_plan = name
        self.project_state_store.write(state)
        return state

    def clear_current(self) -> ProjectState:
        state = self.project_state_store.read()
        state.current_plan = None
        self.project_state_store.write(state)
        return state

    def current_name(self) -> str | None:
        """Return the selected plan's name without loading its document."""
        return self.project_state_store.read().current_plan

    def _task_counts(self, name: Name) -> dict[TaskStatus, int]:
        task_records = self.document_store.list(self.layout.task_collection(name), TaskMetadata)
        task_counts: dict[TaskStatus, int] = {"todo": 0, "in-progress": 0, "done": 0}
        for task in task_records:
            task_counts[task.metadata.status] += 1
        return task_counts

    def _context_count(self, name: Name) -> int:
        return len(self.document_store.list(self.layout.context_collection(name), ContextMetadata))

    @validate_call
    def info(self, name: Name) -> PlanInfo:
        plan = self.get(name)
        return PlanInfo(
            plan=DocumentRecord[PlanMetadata].from_document(
                plan.document,
                name=plan.name,
                path=plan.path,
                last_activity_at=self.document_store.get_last_activity_at(
                    plan.path, self.layout.plan_activity_scopes()
                ),
            ),
            task_counts=self._task_counts(name),
            context_count=self._context_count(name),
        )

    @validate_call
    def plan_overview(self, name: Name) -> PlanOverview:
        return PlanOverview(
            current=self.project_state_store.read().current_plan == name,
            info=self.info(name),
        )

    def project_overview(self) -> ProjectOverview:
        state = self.project_state_store.read()
        plans = self.list()
        plans_by_status: dict[PlanStatus, int] = {"draft": 0, "active": 0, "done": 0}
        task_totals: dict[TaskStatus, int] = {"todo": 0, "in-progress": 0, "done": 0}
        context_count = 0
        for plan in plans:
            plans_by_status[plan.metadata.status] += 1
            context_count += self._context_count(plan.name)
            for status, count in self._task_counts(plan.name).items():
                task_totals[status] += count
        recent_plans = sorted(plans, key=lambda plan: plan.last_activity_at, reverse=True)[:5]
        return ProjectOverview(
            current_plan=state.current_plan,
            selection_valid=state.current_plan is None
            or any(plan.name == state.current_plan for plan in plans),
            plan_count=len(plans),
            plans_by_status=plans_by_status,
            task_totals=task_totals,
            context_count=context_count,
            recent_plans=recent_plans,
        )
