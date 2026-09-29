"""Overview counts built from the resource services."""

from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from machinate.models.documents import ParsedDocument, PlanStatus, TaskMetadata, TaskStatus
from machinate.models.operations import CreateInput, StatusCreateInput
from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.overview import OverviewService
from machinate.services.plan import PlanService
from machinate.services.task import TaskService
from machinate.storage import (
    DocumentStore,
    InvalidDocumentError,
    Layout,
    ProjectState,
    ProjectStateStore,
)


def _overview(tmp_path: Path) -> OverviewService:
    layout = Layout()
    store = DocumentStore(tmp_path / "docs")
    state = ProjectStateStore(tmp_path / "state.toml")
    state.write(ProjectState(project_name="demo"))
    return OverviewService(
        PlanService(store, layout, state),
        TaskService(store, layout),
        ContextService(store, layout),
        DocService(store, layout),
    )


def test_plan_overview_counts_and_ignores_malformed(tmp_path: Path) -> None:
    overview = _overview(tmp_path)
    overview.plans.create("alpha", StatusCreateInput[PlanStatus]())
    empty = overview.plan_overview("alpha")
    assert empty.tasks_by_status == {"todo": 0, "in-progress": 0, "done": 0}
    assert empty.context_count == 0
    for name, status in [
        ("one", "todo"),
        ("nested/two", "done"),
        ("three", "in-progress"),
        ("four", "todo"),
    ]:
        overview.plans.document_store.create(
            PurePosixPath("plans/alpha/tasks", f"{name}.md"),
            ParsedDocument(
                metadata=TaskMetadata.model_validate(
                    {"created_at": datetime(2026, 9, 22, tzinfo=UTC), "status": status}
                ),
                body="",
            ),
        )
    overview.contexts.create("alpha", "nested/note", CreateInput())
    info = overview.plan_overview("alpha")
    assert info.tasks_by_status == {"todo": 2, "in-progress": 1, "done": 1}
    assert info.context_count == 1
    assert info.plan == overview.plans.list_records()[0]

    bad = overview.plans.document_store.root / "plans/alpha/tasks/bad.md"
    bad.write_text("---\nsummary: missing date\n---\n")
    assert len(overview.plans.list_records()) == 1
    with pytest.raises(InvalidDocumentError):
        overview.plan_overview("alpha")


def test_project_overview_counts_plans_tasks_contexts_and_docs(tmp_path: Path) -> None:
    overview = _overview(tmp_path)
    overview.plans.create("alpha", StatusCreateInput[PlanStatus]())
    overview.plans.create("beta", StatusCreateInput[PlanStatus](status="active"))
    overview.tasks.create("alpha", "one", StatusCreateInput[TaskStatus](status="done"))
    overview.contexts.create("alpha", "note", CreateInput())
    overview.docs.create("guide", CreateInput())

    project = overview.project_overview()
    assert project.plan_count == 2
    assert project.plans_by_status == {"draft": 1, "active": 1, "done": 0}
    assert project.tasks_by_status == {"todo": 0, "in-progress": 0, "done": 1}
    assert project.context_count == 1
    assert project.doc_count == 1
    assert project.current_plan is None
    assert project.selection_valid
    assert [plan.name for plan in project.recent_plans] == ["alpha", "beta"]
