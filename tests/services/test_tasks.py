"""Task-specific behavior: batch creation and the shared plan check."""

from datetime import UTC, datetime
from pathlib import Path

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


def test_create_many_rejects_case_only_duplicates(service: TaskService) -> None:
    batch = service.create_many("alpha", ["Login", "login"], StatusCreateInput[TaskStatus]())
    assert [record.name for record in batch.created] == ["Login"]
    assert [failure.name for failure in batch.failures] == ["login"]
    assert batch.failures[0].reason == "exists"


def test_create_many_unknown_plan(service: TaskService) -> None:
    with pytest.raises(NotFoundError):
        service.create_many("missing", ["a"], StatusCreateInput[TaskStatus]())


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
        service.create_many("missing", ["new"], StatusCreateInput[TaskStatus]())
    assert not (service.document_store.root / service.layout.task_path("missing", "new")).exists()
