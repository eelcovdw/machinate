import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from machinate.models.documents import (
    ParsedDocument,
    PlanMetadata,
    PlanStatus,
    TaskMetadata,
    TaskStatus,
)
from machinate.models.operations import StatusCreateInput, StatusUpdate, TaskQuery
from machinate.services.plan import PlanService
from machinate.services.task import TaskService
from machinate.storage import (
    DocumentExistsError,
    DocumentStore,
    Layout,
    MissingDocumentError,
    ProjectState,
    ProjectStateStore,
)


@pytest.fixture
def service(tmp_path: Path) -> TaskService:
    store = DocumentStore(tmp_path / "docs")
    store.create(
        Layout().plan("alpha"),
        ParsedDocument(
            metadata=PlanMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC)), body=""
        ),
    )
    return TaskService(store, Layout())


@pytest.fixture
def metadata() -> TaskMetadata:
    return TaskMetadata.model_validate(
        {"created_at": "2026-09-22T00:00:00Z", "custom": {"owner": "Alice"}}
    )


def test_create_get_duplicates_and_exact_names(service: TaskService) -> None:
    create = StatusCreateInput[TaskStatus](summary="Login flow", tags=["auth"])
    task = service.create("alpha", "login", create)
    service.document_store.write(
        service.path("alpha", "login"),
        ParsedDocument(metadata=task.record.metadata, body="Body\n"),
    )
    task = service.get("alpha", "login")
    assert task == service.get("alpha", "login")
    assert task.record.path == PurePosixPath("plans/alpha/tasks/login.md")
    assert task.body == "Body\n"
    assert task.record.metadata.summary == "Login flow"
    assert task.record.metadata.tags == ["auth"]
    assert task.record.metadata.created_at.tzinfo is not None
    assert json.loads(task.model_dump_json())["record"]["path"] == "plans/alpha/tasks/login.md"
    with pytest.raises(DocumentExistsError):
        service.create("alpha", "login", StatusCreateInput[TaskStatus]())
    with pytest.raises(MissingDocumentError):
        service.get("alpha", "log")


def test_create_batch_reports_partial_results(service: TaskService) -> None:
    """C2: existing and invalid names become errors; later names still get created."""
    service.create("alpha", "existing", StatusCreateInput[TaskStatus]())
    batch = service.create_batch(
        "alpha", ["new", "existing", "../bad", "later"], StatusCreateInput[TaskStatus]()
    )
    assert [task.record.name for task in batch.created] == ["new", "later"]
    assert [error.name for error in batch.errors] == ["existing", "../bad"]
    assert service.get("alpha", "new")
    assert service.get("alpha", "later")


def test_create_batch_rejects_case_only_duplicates(service: TaskService) -> None:
    batch = service.create_batch("alpha", ["Login", "login"], StatusCreateInput[TaskStatus]())
    assert [task.record.name for task in batch.created] == ["Login"]
    assert [error.name for error in batch.errors] == ["login"]


def test_create_batch_empty(service: TaskService) -> None:
    batch = service.create_batch("alpha", [], StatusCreateInput[TaskStatus]())
    assert batch.created == []
    assert batch.errors == []


def test_create_batch_unknown_plan(service: TaskService) -> None:
    with pytest.raises(MissingDocumentError):
        service.create_batch("missing", ["a"], StatusCreateInput[TaskStatus]())


def test_create_batch_reads_plan_once(
    service: TaskService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan is validated once, not once per name (N+1)."""
    read = Mock(wraps=service.document_store.read)
    monkeypatch.setattr(service.document_store, "read", read)
    service.create_batch("alpha", ["one", "two", "three"], StatusCreateInput[TaskStatus]())
    plan_path = service.layout.plan("alpha")
    plan_reads = [call for call in read.call_args_list if call.args[0] == plan_path]
    assert len(plan_reads) == 1


def test_patches(service: TaskService, metadata: TaskMetadata) -> None:
    service.document_store.create(
        service.layout.task("alpha", "login"), ParsedDocument(metadata=metadata, body="Body")
    )
    task = service.update("alpha", "login", StatusUpdate[TaskStatus](status="in-progress"))
    assert task.body == "Body"
    assert task.record.metadata.status == "in-progress"
    assert task.record.summary == "Body"
    service.document_store.write(
        service.path("alpha", "login"),
        ParsedDocument(metadata=task.record.metadata, body=""),
    )
    task = service.get("alpha", "login")
    assert task.body == ""
    assert task.record.metadata.status == "in-progress"
    assert task.record.summary is None
    assert task.record.metadata.created_at.tzinfo is not None
    assert task.record.metadata.model_extra == metadata.model_extra


def test_empty_patch(service: TaskService, monkeypatch: pytest.MonkeyPatch) -> None:
    task = service.create("alpha", "login", StatusCreateInput[TaskStatus]())
    target = service.document_store.root / task.record.path
    os.utime(target, ns=(1234567890123456789, 1234567890123456789))
    before = target.read_bytes(), target.stat().st_mtime_ns
    task = service.get("alpha", "login")
    write = Mock(side_effect=AssertionError("empty patch must not write"))
    monkeypatch.setattr(service.document_store, "write", write)
    assert service.update("alpha", "login", StatusUpdate[TaskStatus]()) == task
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    write.assert_not_called()


@pytest.mark.parametrize("plan", ["alpha", "missing"])
def test_missing_tasks_and_plans(service: TaskService, metadata: TaskMetadata, plan: str) -> None:
    for operation in (
        lambda: service.get(plan, "missing"),
        lambda: service.update(plan, "missing", StatusUpdate[TaskStatus]()),
        lambda: service.update(plan, "missing", StatusUpdate[TaskStatus](status="done")),
    ):
        with pytest.raises(MissingDocumentError):
            operation()
    if plan == "missing":
        # Even an orphan task cannot make a missing plan valid.
        service.document_store.create(
            service.layout.task(plan, "missing"), ParsedDocument(metadata=metadata, body="")
        )
        with pytest.raises(MissingDocumentError):
            service.get(plan, "missing")
        with pytest.raises(MissingDocumentError):
            service.list(plan)
        with pytest.raises(MissingDocumentError):
            service.create(plan, "new", StatusCreateInput[TaskStatus]())
        assert not (service.document_store.root / service.layout.task(plan, "new")).exists()
    else:
        assert service.list(plan) == []


@pytest.mark.parametrize(
    "name",
    ["", "/abs", "../x", "a/../x", "a/./x", "a//x", "a/", "a/ x", "a/x ", "C:/x", "a\\x", "a/\nx"],
)
def test_invalid_names(service: TaskService, name: str) -> None:
    with pytest.raises(ValidationError):
        service.create("alpha", name, StatusCreateInput[TaskStatus]())
    with pytest.raises(ValidationError):
        service.get("alpha", name)


def test_nested_round_trip_and_query(service: TaskService) -> None:
    for name in ("nested/login", "other/login", "login.v2"):
        service.create("alpha", name, StatusCreateInput[TaskStatus]())
    for record in service.list("alpha"):
        task = service.get("alpha", record.name)
        assert task.record.path == record.path
        assert task.record.modified_at == record.modified_at
        assert "body" not in record.model_dump()
        service.update("alpha", record.name, StatusUpdate[TaskStatus](status="done"))
    service.document_store.write(
        service.path("alpha", "nested/login"),
        ParsedDocument(metadata=service.get("alpha", "nested/login").record.metadata, body="OAuth"),
    )
    assert service.get("alpha", "nested/login").body == "OAuth"
    found = service.list("alpha", TaskQuery(statuses={"done"}))
    assert [task.name for task in found] == ["login.v2", "nested/login", "other/login"]


def test_explicit_plan_isolation(service: TaskService, tmp_path: Path) -> None:
    state = ProjectStateStore(tmp_path / "state.toml")
    state.write(ProjectState(project_name="demo"))
    plans = PlanService(service.document_store, service.layout, state)
    plans.create("beta", StatusCreateInput[PlanStatus]())
    plans.set_current("alpha")
    beta = service.create("beta", "login", StatusCreateInput[TaskStatus]())
    service.document_store.write(
        service.path("beta", "login"),
        ParsedDocument(metadata=beta.record.metadata, body="Beta"),
    )
    plans.set_current("beta")
    service.create("alpha", "login", StatusCreateInput[TaskStatus]())
    service.document_store.write(
        service.path("alpha", "login"),
        ParsedDocument(metadata=service.get("alpha", "login").record.metadata, body="Alpha"),
    )
    service.update("alpha", "login", StatusUpdate[TaskStatus](status="done"))
    assert service.get("beta", "login").body == "Beta"
    assert service.list("beta")[0].metadata == beta.record.metadata
    assert service.list("alpha")[0].metadata.status == "done"
    assert state.read().current_plan == "beta"
