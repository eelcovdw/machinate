import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from machinate.models.plan import PlanUpdate
from machinate.services.plan import PlanService
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentExistsError,
    DocumentStore,
    InvalidDocumentError,
    Layout,
    MissingDocumentError,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
    TaskMetadata,
)


@pytest.fixture
def service(tmp_path: Path) -> PlanService:
    state = ProjectStateStore(tmp_path / "state.toml")
    state.write(ProjectState(project_name="demo"))
    return PlanService(DocumentStore(tmp_path / "docs"), Layout(), state)


@pytest.fixture
def metadata() -> PlanMetadata:
    return PlanMetadata.model_validate(
        {"created": "2026-09-22T00:00:00Z", "custom": {"owner": "Alice"}}
    )


def test_create_get_and_duplicate(service: PlanService, metadata: PlanMetadata) -> None:
    plan = service.create("alpha", metadata, "Body\n")
    assert plan == service.get("alpha")
    assert plan.name == "alpha"
    assert plan.path == PurePosixPath("plans/alpha/plan.md")
    assert plan.document == Document(metadata=metadata, body="Body\n")
    assert service.current_name() is None
    assert service.project_state_store.read() == ProjectState(project_name="demo")
    assert '"created":"2026-09-22T00:00:00Z"' in plan.model_dump_json()
    with pytest.raises(DocumentExistsError):
        service.create("alpha", metadata)


def test_patch_preserves_omitted_fields_and_extra_metadata(
    service: PlanService, metadata: PlanMetadata
) -> None:
    service.create("alpha", metadata, "Body")
    result = service.update("alpha", PlanUpdate(status="active"))
    assert result.document.body == "Body"
    assert result.document.metadata.status == "active"
    assert result.document.get_or_derive_summary() == "Body"
    result = service.update("alpha", PlanUpdate(body=""))
    assert result.document.body == ""
    assert result.document.metadata.status == "active"
    assert result.document.get_or_derive_summary() is None
    assert result.document.metadata.created == metadata.created
    assert result.document.metadata.model_extra == metadata.model_extra


def test_empty_patch_never_writes(
    service: PlanService, metadata: PlanMetadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.create("alpha", metadata, "Body")
    target = service.document_store.root / "plans/alpha/plan.md"
    os.utime(target, ns=(1234567890123456789, 1234567890123456789))
    before = target.read_bytes(), target.stat().st_mtime_ns
    write = Mock(side_effect=AssertionError("empty patch must not write"))
    monkeypatch.setattr(service.document_store, "write", write)
    result = service.update("alpha", PlanUpdate())
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    assert result.modified_at == datetime.fromtimestamp(target.stat().st_mtime, UTC)
    write.assert_not_called()


def test_missing_operations_and_dangling_selection(service: PlanService) -> None:
    for operation in (service.get, service.set_current, service.info):
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


def test_selection_does_not_retarget_explicit_operations(
    service: PlanService, metadata: PlanMetadata
) -> None:
    service.create("alpha", metadata)
    assert service.set_current("alpha") == ProjectState(project_name="demo", current_plan="alpha")
    service.create("beta", metadata)
    assert service.current_name() == "alpha"
    service.set_current("beta")
    service.update("alpha", PlanUpdate(body="only alpha"))
    service.update("alpha", PlanUpdate(status="done"))
    assert service.get("alpha").document.body == "only alpha"
    assert service.get("beta").document.body == ""
    assert service.current_name() == "beta"
    assert service.info("alpha").plan.metadata.status == "done"
    assert service.project_state_store.read().project_name == "demo"


def test_info_counts_and_list_ignores_malformed_children(
    service: PlanService, metadata: PlanMetadata
) -> None:
    service.create("alpha", metadata)
    empty = service.info("alpha")
    assert empty.task_counts == {"todo": 0, "in-progress": 0, "done": 0}
    assert empty.context_count == 0
    for name, status in [
        ("one", "todo"),
        ("nested/two", "done"),
        ("three", "in-progress"),
        ("four", "todo"),
    ]:
        service.document_store.create(
            PurePosixPath("plans/alpha/tasks", f"{name}.md"),
            Document(
                metadata=TaskMetadata.model_validate(
                    {"created": datetime(2026, 9, 22, tzinfo=UTC), "status": status}
                ),
                body="",
            ),
        )
    service.document_store.create(
        PurePosixPath("plans/alpha/context/nested/note.md"),
        Document(metadata=ContextMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body=""),
    )
    info = service.info("alpha")
    assert info.task_counts == {"todo": 2, "in-progress": 1, "done": 1}
    assert info.context_count == 1
    assert info.plan == service.list()[0]
    bad = service.document_store.root / "plans/alpha/tasks/bad.md"
    bad.write_text("---\nsummary: missing date\n---\n")
    assert len(service.list()) == 1
    with pytest.raises(InvalidDocumentError):
        service.info("alpha")
