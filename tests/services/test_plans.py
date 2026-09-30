"""Plan-specific behavior: selection, dangling selection, and activity."""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from machinate.models.documents import ParsedDocument, PlanStatus, TaskMetadata
from machinate.models.operations import StatusCreateInput, StatusUpdate
from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.errors import NotFoundError
from machinate.services.overview import OverviewService
from machinate.services.plan import PlanService
from machinate.services.task import TaskService
from machinate.storage import DocumentStore, Layout, ProjectState, ProjectStateStore


@pytest.fixture
def state(tmp_path: Path) -> ProjectStateStore:
    project_state = ProjectStateStore(tmp_path / "state.toml")
    project_state.write(ProjectState(project_name="demo"))
    return project_state


@pytest.fixture
def service(tmp_path: Path, state: ProjectStateStore) -> PlanService:
    return PlanService(DocumentStore(tmp_path / "docs"), Layout(), state)


def test_selection_does_not_retarget_explicit_operations(service: PlanService) -> None:
    service.create("alpha", StatusCreateInput[PlanStatus]())
    assert service.select_plan("alpha") == ProjectState(project_name="demo", current_plan="alpha")
    service.create("beta", StatusCreateInput[PlanStatus]())
    assert service.find_current_plan() == "alpha"
    service.select_plan("beta")
    alpha = service.get("alpha")
    service.document_store.write(
        alpha.record.path,
        ParsedDocument(metadata=alpha.record.metadata, body="only alpha"),
    )
    service.update("alpha", StatusUpdate[PlanStatus](status="done"))
    assert service.get("alpha").body == "only alpha"
    assert service.get("beta").body == ""
    assert service.find_current_plan() == "beta"
    assert service.project_state_store.read().project_name == "demo"
    assert service.unselect_plan() == ProjectState(project_name="demo")
    assert service.find_current_plan() is None


def test_missing_operations_and_dangling_selection(
    service: PlanService, state: ProjectStateStore
) -> None:
    for operation in (service.select_plan,):
        with pytest.raises(NotFoundError):
            operation("missing")
    assert service.find_current_plan() is None
    state.write(ProjectState(project_name="demo", current_plan="missing"))
    assert service.find_current_plan() == "missing"
    with pytest.raises(NotFoundError):
        service.get(service.find_current_plan() or "")


def test_plan_activity_matches_across_show_list_and_info(
    tmp_path: Path, state: ProjectStateStore
) -> None:
    layout = Layout()
    store = DocumentStore(tmp_path / "docs")
    service = PlanService(store, layout, state)
    overview = OverviewService(
        service,
        TaskService(store, layout),
        ContextService(store, layout),
        DocService(store, layout),
    )
    service.create("alpha", StatusCreateInput[PlanStatus]())
    service.document_store.create(
        layout.task_path("alpha", "01-work"),
        ParsedDocument(
            metadata=TaskMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC)), body=""
        ),
    )
    newest = datetime.fromtimestamp(2_000_000_000, UTC)
    os.utime(
        service.document_store.root / "plans/alpha/tasks/01-work.md",
        (2_000_000_000, 2_000_000_000),
    )

    shown = service.get("alpha").record.last_activity_at
    listed = service.list_records()[0].last_activity_at
    info = overview.get_plan_overview("alpha").plan.last_activity_at

    assert shown == listed == info == newest
