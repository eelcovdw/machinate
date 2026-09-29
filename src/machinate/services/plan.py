"""Plan documents: top-level, status-bearing, with selection and activity."""

from datetime import UTC, datetime
from pathlib import PurePosixPath
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
    BatchCreated,
    PlanQuery,
    StatusCreateInput,
    StatusUpdate,
)
from machinate.services.document import Collection, DocumentService, LocatedPath
from machinate.storage import DocumentStore, Layout, ProjectState, ProjectStateStore


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
                storage=lambda _plan: layout.plan_collection(),
                path=lambda _plan, name: layout.plan(name),
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
            last_activity_at=self.document_store.get_last_activity_at(
                record.path, self.layout.plan_collection().activity_scopes
            ),
        )

    def _plan_loaded(self, loaded: LoadedDocument[PlanMetadata]) -> LoadedPlan:
        return LoadedPlan(record=self._plan_record(loaded.record), body=loaded.body)

    @validate_call
    def create(self, name: Name, create: StatusCreateInput[PlanStatus]) -> LoadedPlan:
        return self._plan_loaded(self._create(None, name, create))

    @validate_call
    def create_batch(
        self, names: list[str], create: StatusCreateInput[PlanStatus]
    ) -> BatchCreated[LoadedPlan]:
        batch = self._create_batch(None, names, create)
        return BatchCreated(
            created=[self._plan_loaded(loaded) for loaded in batch.created],
            errors=batch.errors,
        )

    @validate_call
    def info(self, name: Name) -> PlanRecord:
        return self._plan_record(self._info(None, name))

    @validate_call
    def path(self, name: Name) -> PurePosixPath:
        return self._path(None, name)

    @validate_call
    def directory(self) -> PurePosixPath:
        return self._directory(None)

    @validate_call
    def locate(self, name: Name) -> LocatedPath:
        return self._locate(None, name)

    @validate_call
    def get(self, name: Name) -> LoadedPlan:
        return self._plan_loaded(self._get(None, name))

    @validate_call
    def update(self, name: Name, changes: StatusUpdate[PlanStatus]) -> LoadedPlan:
        return self._plan_loaded(self._update(None, name, changes))

    @validate_call
    def list_records(self, query: PlanQuery | None = None) -> list[PlanRecord]:
        return [self._plan_record(record) for record in self._list(None, query)]

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
