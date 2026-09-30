"""Task-specific behavior: batch creation and the shared plan check."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from machinate.models.documents import ParsedDocument, PlanMetadata, TaskMetadata, TaskStatus
from machinate.models.operations import StatusCreateInput
from machinate.services.errors import NotFoundError
from machinate.services.task import TaskService
from machinate.storage import DocumentStore, Layout


@pytest.fixture
def service(tmp_path: Path) -> TaskService:
    store = DocumentStore(tmp_path / "docs")
    store.create(
        Layout().plan_path("alpha"),
        ParsedDocument(
            metadata=PlanMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC)), body=""
        ),
    )
    return TaskService(store, Layout())


def test_create_many_reports_partial_results(service: TaskService) -> None:
    service.create("alpha", "existing", StatusCreateInput[TaskStatus]())
    batch = service.create_many(
        "alpha", ["new", "existing", "../bad", "later"], StatusCreateInput[TaskStatus]()
    )
    assert [record.name for record in batch.created] == ["new", "later"]
    assert [failure.name for failure in batch.failures] == ["existing", "../bad"]
    assert [failure.reason for failure in batch.failures] == ["exists", "invalid_name"]
    assert service.get("alpha", "new")
    assert service.get("alpha", "later")


def test_create_many_rejects_case_only_duplicates(service: TaskService) -> None:
    batch = service.create_many("alpha", ["Login", "login"], StatusCreateInput[TaskStatus]())
    assert [record.name for record in batch.created] == ["Login"]
    assert [failure.name for failure in batch.failures] == ["login"]
    assert batch.failures[0].reason == "exists"


def test_create_many_empty(service: TaskService) -> None:
    batch = service.create_many("alpha", [], StatusCreateInput[TaskStatus]())
    assert batch.created == []
    assert batch.failures == []


def test_create_many_unknown_plan(service: TaskService) -> None:
    with pytest.raises(NotFoundError):
        service.create_many("missing", ["a"], StatusCreateInput[TaskStatus]())


def test_create_many_reads_plan_once(service: TaskService, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plan is validated once, not once per name (N+1)."""
    metadata = Mock(wraps=service.document_store.stat)
    monkeypatch.setattr(service.document_store, "stat", metadata)
    service.create_many("alpha", ["one", "two", "three"], StatusCreateInput[TaskStatus]())
    plan_path = service.layout.plan_path("alpha")
    plan_reads = [call for call in metadata.call_args_list if call.args[0] == plan_path]
    assert len(plan_reads) == 1


def test_orphan_task_cannot_make_a_missing_plan_valid(service: TaskService) -> None:
    metadata = TaskMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC))
    service.document_store.create(
        service.layout.task_path("missing", "orphan"), ParsedDocument(metadata=metadata, body="")
    )
    with pytest.raises(NotFoundError):
        service.get("missing", "orphan")
    with pytest.raises(NotFoundError):
        service.list_records("missing")
    with pytest.raises(NotFoundError):
        service.create("missing", "new", StatusCreateInput[TaskStatus]())
    assert not (service.document_store.root / service.layout.task_path("missing", "new")).exists()
