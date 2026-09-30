"""Plan documents: top-level, status-bearing, with selection and activity."""

from datetime import UTC, datetime
from typing import override

from pydantic import validate_call

from machinate.models.documents import (
    DocumentRecord,
    LoadedDocument,
    LoadedPlan,
    Name,
    PlanMetadata,
    PlanRecord,
    PlanStatus,
)
from machinate.models.operations import (
    PlanQuery,
    StatusCreateInput,
    StatusUpdate,
)
from machinate.services.document import Collection, DocumentService, LocatedPath
from machinate.storage.document_store import DocumentStore
from machinate.storage.layout import Layout
from machinate.storage.models import ProjectState
from machinate.storage.project_state_store import ProjectStateStore


class PlanService(DocumentService[PlanMetadata, StatusCreateInput[PlanStatus]]):
    def __init__(
        self, document_store: DocumentStore, layout: Layout, project_state_store: ProjectStateStore
    ) -> None:
        super().__init__(
            document_store,
            layout,
            Collection(
                kind="plan",
                metadata_type=PlanMetadata,
                collection=lambda _plan: layout.plan_collection(),
                path=lambda _plan, name: layout.plan_path(name),
                requires_plan=False,
                directory_kind=None,
            ),
        )
        self.project_state_store: ProjectStateStore = project_state_store

    @override
    def _build_metadata(self, create: StatusCreateInput[PlanStatus]) -> PlanMetadata:
        return PlanMetadata(
            created_at=datetime.now(UTC),
            summary=create.summary or None,
            tags=create.tags,
            status=create.status or "draft",
        )

    def _plan_record(self, record: DocumentRecord[PlanMetadata]) -> PlanRecord:
        return PlanRecord(
            name=record.name,
            path=record.path,
            metadata=record.metadata,
            modified_at=record.modified_at,
            summary=record.summary,
            last_activity_at=self.document_store.read_last_activity_at(
                record.path,
                self.layout.task_collection(record.name),
                self.layout.context_collection(record.name),
            ),
        )

    def _plan_loaded(self, loaded: LoadedDocument[PlanMetadata]) -> LoadedPlan:
        return LoadedPlan(record=self._plan_record(loaded.record), body=loaded.body)

    @validate_call
    def create(self, name: Name, create: StatusCreateInput[PlanStatus]) -> LoadedPlan:
        return self._plan_loaded(self._create(None, name, create))

    @validate_call
    def get_record(self, name: Name) -> PlanRecord:
        return self._plan_record(self._info(None, name))

    @validate_call
    def locate(self, name: Name) -> LocatedPath:
        return self._locate(None, name)

    @validate_call
    def get(self, name: Name) -> LoadedPlan:
        return self._plan_loaded(self._get(None, name))

    @validate_call
    def update(self, name: Name, update: StatusUpdate[PlanStatus]) -> LoadedPlan:
        return self._plan_loaded(self._update(None, name, update))

    @validate_call
    def list_records(self, query: PlanQuery | None = None) -> list[PlanRecord]:
        active = query or PlanQuery()
        if active.sort == "last_activity_at":
            base = active.model_copy(update={"sort": "name", "limit": None})
            records = [self._plan_record(record) for record in self._list(None, base)]
            records.sort(key=lambda record: record.last_activity_at, reverse=active.descending)
            return records if active.limit is None else records[: active.limit]
        return [self._plan_record(record) for record in self._list(None, active)]

    @validate_call
    def select_plan(self, name: Name) -> ProjectState:
        self.require_plan(name)
        state = self.project_state_store.read()
        state.current_plan = name
        self.project_state_store.write(state)
        return state

    def unselect_plan(self) -> ProjectState:
        state = self.project_state_store.read()
        state.current_plan = None
        self.project_state_store.write(state)
        return state

    def find_current_plan(self) -> str | None:
        """Return the selected plan's name without loading its document."""
        return self.project_state_store.read().current_plan
