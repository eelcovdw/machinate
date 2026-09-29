import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from machinate.models.documents import (
    ContextMetadata,
    ParsedDocument,
    PlanMetadata,
    PlanStatus,
    TaskMetadata,
)
from machinate.models.operations import PlanUpdate, StatusCreateInput
from machinate.services.plan import PlanService
from machinate.storage import (
    DocumentExistsError,
    DocumentStore,
    InvalidDocumentError,
    Layout,
    MissingDocumentError,
    ProjectState,
    ProjectStateStore,
)


@pytest.fixture
def service(tmp_path: Path) -> PlanService:
    state = ProjectStateStore(tmp_path / "state.toml")
    state.write(ProjectState(project_name="demo"))
    return PlanService(DocumentStore(tmp_path / "docs"), Layout(), state)


@pytest.fixture
def metadata() -> PlanMetadata:
    return PlanMetadata.model_validate(
        {"created_at": "2026-09-22T00:00:00Z", "custom": {"owner": "Alice"}}
    )


def test_create_get_and_duplicate(service: PlanService) -> None:
    plan = service.create("alpha", StatusCreateInput[PlanStatus](summary="Alpha"), "Body\n")
    assert plan == service.get("alpha")
    assert plan.record.name == "alpha"
    assert plan.record.path == PurePosixPath("plans/alpha/plan.md")
    assert plan.body == "Body\n"
    assert plan.record.metadata.summary == "Alpha"
    assert plan.record.metadata.status == "draft"
    assert plan.record.metadata.created_at.tzinfo is not None
    assert service.current_name() is None
    assert service.project_state_store.read() == ProjectState(project_name="demo")
    with pytest.raises(DocumentExistsError):
        service.create("alpha", StatusCreateInput[PlanStatus]())


def test_plan_activity_matches_across_show_list_and_info(service: PlanService) -> None:
    service.create("alpha", StatusCreateInput[PlanStatus](), "Body")
    service.document_store.create(
        PurePosixPath("plans/alpha/tasks/01-work.md"),
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
    listed = service.list()[0].last_activity_at
    info = service.plan_overview("alpha").plan.last_activity_at

    assert shown == listed == info == newest


def test_patch_preserves_omitted_fields_and_extra_metadata(
    service: PlanService, metadata: PlanMetadata
) -> None:
    service.document_store.create(
        service.layout.plan("alpha"), ParsedDocument(metadata=metadata, body="Body")
    )
    result = service.update("alpha", PlanUpdate(status="active"))
    assert result.body == "Body"
    assert result.record.metadata.status == "active"
    assert result.record.summary == "Body"
    assert result.record.metadata.created_at.tzinfo is not None
    result = service.update("alpha", PlanUpdate(body=""))
    assert result.body == ""
    assert result.record.metadata.status == "active"
    assert result.record.summary is None
    assert result.record.metadata.model_extra == metadata.model_extra


def test_empty_patch_never_writes(service: PlanService, monkeypatch: pytest.MonkeyPatch) -> None:
    service.create("alpha", StatusCreateInput[PlanStatus](), "Body")
    target = service.document_store.root / "plans/alpha/plan.md"
    os.utime(target, ns=(1234567890123456789, 1234567890123456789))
    before = target.read_bytes(), target.stat().st_mtime_ns
    write = Mock(side_effect=AssertionError("empty patch must not write"))
    monkeypatch.setattr(service.document_store, "write", write)
    result = service.update("alpha", PlanUpdate())
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    assert result.record.modified_at == datetime.fromtimestamp(target.stat().st_mtime, UTC)
    write.assert_not_called()


def test_missing_operations_and_dangling_selection(service: PlanService) -> None:
    for operation in (service.get, service.set_current, service.plan_overview):
        with pytest.raises(MissingDocumentError):
            operation("missing")
    with pytest.raises(MissingDocumentError):
        service.update("missing", PlanUpdate())
    with pytest.raises(MissingDocumentError):
        service.update("missing", PlanUpdate(status="done"))
    assert service.current_name() is None
    service.project_state_store.write(ProjectState(project_name="demo", current_plan="missing"))
    assert service.current_name() == "missing"
    with pytest.raises(MissingDocumentError):
        service.get(service.current_name() or "")


def test_selection_does_not_retarget_explicit_operations(service: PlanService) -> None:
    service.create("alpha", StatusCreateInput[PlanStatus]())
    assert service.set_current("alpha") == ProjectState(project_name="demo", current_plan="alpha")
    service.create("beta", StatusCreateInput[PlanStatus]())
    assert service.current_name() == "alpha"
    service.set_current("beta")
    service.update("alpha", PlanUpdate(body="only alpha"))
    service.update("alpha", PlanUpdate(status="done"))
    assert service.get("alpha").body == "only alpha"
    assert service.get("beta").body == ""
    assert service.current_name() == "beta"
    assert service.plan_overview("alpha").plan.metadata.status == "done"
    assert service.project_state_store.read().project_name == "demo"


def test_info_counts_and_list_ignores_malformed_children(service: PlanService) -> None:
    service.create("alpha", StatusCreateInput[PlanStatus]())
    empty = service.plan_overview("alpha")
    assert empty.tasks_by_status == {"todo": 0, "in-progress": 0, "done": 0}
    assert empty.context_count == 0
    for name, status in [
        ("one", "todo"),
        ("nested/two", "done"),
        ("three", "in-progress"),
        ("four", "todo"),
    ]:
        service.document_store.create(
            PurePosixPath("plans/alpha/tasks", f"{name}.md"),
            ParsedDocument(
                metadata=TaskMetadata.model_validate(
                    {"created_at": datetime(2026, 9, 22, tzinfo=UTC), "status": status}
                ),
                body="",
            ),
        )
    service.document_store.create(
        PurePosixPath("plans/alpha/context/nested/note.md"),
        ParsedDocument(
            metadata=ContextMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC)), body=""
        ),
    )
    info = service.plan_overview("alpha")
    assert info.tasks_by_status == {"todo": 2, "in-progress": 1, "done": 1}
    assert info.context_count == 1
    assert info.plan == service.list()[0]
    bad = service.document_store.root / "plans/alpha/tasks/bad.md"
    bad.write_text("---\nsummary: missing date\n---\n")
    assert len(service.list()) == 1
    with pytest.raises(InvalidDocumentError):
        service.plan_overview("alpha")
