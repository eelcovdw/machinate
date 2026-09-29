from datetime import UTC, datetime
from pathlib import PurePosixPath

from pydantic import validate_call

from machinate.models.documents import (
    ContextMetadata,
    LoadedPlan,
    Name,
    ParsedDocument,
    PlanMetadata,
    PlanRecord,
    PlanStatus,
    TaskMetadata,
    TaskStatus,
)
from machinate.models.operations import (
    PlanOverview,
    PlanQuery,
    ProjectOverview,
    StatusCreateInput,
    StatusUpdate,
)
from machinate.storage import DocumentStore, Layout, ProjectState, ProjectStateStore


class PlanService:
    def __init__(
        self, document_store: DocumentStore, layout: Layout, project_state_store: ProjectStateStore
    ) -> None:
        self.document_store: DocumentStore = document_store
        self.layout: Layout = layout
        self.project_state_store: ProjectStateStore = project_state_store

    def _record(
        self,
        path: PurePosixPath,
        name: Name,
        document: ParsedDocument[PlanMetadata],
    ) -> PlanRecord:
        """Build a plan record, statting the file once and walking descendants for activity."""
        return PlanRecord(
            name=name,
            path=path,
            metadata=document.metadata,
            modified_at=self.document_store.metadata(path).modified_at,
            last_activity_at=self.document_store.get_last_activity_at(
                path, self.layout.plan_collection().activity_scopes
            ),
            summary=document.get_or_derive_summary(),
        )

    def _loaded(
        self, path: PurePosixPath, name: Name, document: ParsedDocument[PlanMetadata]
    ) -> LoadedPlan:
        return LoadedPlan(record=self._record(path, name, document), body=document.body)

    @validate_call
    def create(self, name: Name, create: StatusCreateInput[PlanStatus]) -> LoadedPlan:
        metadata = PlanMetadata(
            created_at=datetime.now(UTC),
            summary=create.summary,
            tags=create.tags,
            status=create.status if create.status is not None else "draft",
        )
        self.document_store.create(
            self.layout.plan(name), ParsedDocument(metadata=metadata, body="")
        )
        return self.get(name)

    @validate_call
    def path(self, name: Name) -> PurePosixPath:
        """Store-relative plan path; validates the plan exists without parsing."""
        target = self.layout.plan(name)
        self.document_store.metadata(target)
        return target

    @validate_call
    def get(self, name: Name) -> LoadedPlan:
        path = self.layout.plan(name)
        return self._loaded(path, name, self.document_store.read(path, PlanMetadata))

    @validate_call
    def update(self, name: Name, changes: StatusUpdate[PlanStatus]) -> LoadedPlan:
        path = self.layout.plan(name)
        document = self.document_store.read(path, PlanMetadata)
        updated = changes.apply_to(document)
        if updated is not None:
            self.document_store.write(path, updated)
            document = updated
        return self._loaded(path, name, document)

    @validate_call
    def list(self, query: PlanQuery | None = None) -> list[PlanRecord]:
        scopes = self.layout.plan_collection().activity_scopes
        return [
            PlanRecord(
                name=record.name,
                path=record.path,
                metadata=record.metadata,
                modified_at=record.modified_at,
                last_activity_at=self.document_store.get_last_activity_at(record.path, scopes),
                summary=record.summary,
            )
            for record in self.document_store.list(
                self.layout.plan_collection(), PlanMetadata, query
            )
        ]

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

    def _tasks_by_status(self, name: Name) -> dict[TaskStatus, int]:
        task_records = self.document_store.list(self.layout.task_collection(name), TaskMetadata)
        tasks_by_status: dict[TaskStatus, int] = {"todo": 0, "in-progress": 0, "done": 0}
        for task in task_records:
            tasks_by_status[task.metadata.status] += 1
        return tasks_by_status

    def _context_count(self, name: Name) -> int:
        return len(self.document_store.list(self.layout.context_collection(name), ContextMetadata))

    @validate_call
    def plan_overview(self, name: Name) -> PlanOverview:
        path = self.layout.plan(name)
        document = self.document_store.read(path, PlanMetadata)
        return PlanOverview(
            current=self.project_state_store.read().current_plan == name,
            plan=self._record(path, name, document),
            tasks_by_status=self._tasks_by_status(name),
            context_count=self._context_count(name),
        )

    def project_overview(self) -> ProjectOverview:
        state = self.project_state_store.read()
        plans = self.list()
        plans_by_status: dict[PlanStatus, int] = {"draft": 0, "active": 0, "done": 0}
        tasks_by_status: dict[TaskStatus, int] = {"todo": 0, "in-progress": 0, "done": 0}
        context_count = 0
        for plan in plans:
            plans_by_status[plan.metadata.status] += 1
            context_count += self._context_count(plan.name)
            for status, count in self._tasks_by_status(plan.name).items():
                tasks_by_status[status] += count
        recent_plans = sorted(plans, key=lambda plan: plan.last_activity_at, reverse=True)[:5]
        return ProjectOverview(
            current_plan=state.current_plan,
            selection_valid=state.current_plan is None
            or any(plan.name == state.current_plan for plan in plans),
            plan_count=len(plans),
            plans_by_status=plans_by_status,
            tasks_by_status=tasks_by_status,
            context_count=context_count,
            recent_plans=recent_plans,
        )
