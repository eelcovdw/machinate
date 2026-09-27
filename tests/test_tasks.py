import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from upath import UPath

from machinate.models.task import TaskUpdate
from machinate.services.plan import PlanService
from machinate.services.task import TaskService
from machinate.storage import (
    Document,
    DocumentExistsError,
    DocumentStore,
    Layout,
    MissingDocumentError,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
    TaskMetadata,
    TaskQuery,
)


@pytest.fixture
def service(tmp_path: Path) -> TaskService:
    store = DocumentStore(UPath(tmp_path / "docs"))
    store.create(
        Layout().plan("alpha"),
        Document(metadata=PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body=""),
    )
    return TaskService(store, Layout())


@pytest.fixture
def metadata() -> TaskMetadata:
    return TaskMetadata.model_validate(
        {"created": "2026-09-22T00:00:00Z", "custom": {"owner": "Alice"}}
    )


def test_create_get_duplicates_and_exact_names(
    service: TaskService, metadata: TaskMetadata
) -> None:
    task = service.create("alpha", "login", metadata, "Body\n")
    assert task == service.get("alpha", "login")
    assert task.path == PurePosixPath("plans/alpha/tasks/login.md")
    assert task.document == Document(metadata=metadata, body="Body\n")
    assert json.loads(task.model_dump_json())["path"] == "plans/alpha/tasks/login.md"
    with pytest.raises(DocumentExistsError):
        service.create("alpha", "login", metadata)
    with pytest.raises(MissingDocumentError):
        service.get("alpha", "log")
    with pytest.raises(MissingDocumentError):
        service.get("alpha", "LOGIN")


def test_create_batch_reports_partial_results(service: TaskService, metadata: TaskMetadata) -> None:
    """C2: existing and invalid names become errors; later names still get created."""
    service.create("alpha", "existing", metadata)
    created, errors = service.create_batch(
        "alpha", ["new", "existing", "../bad", "later"], metadata
    )
    assert [task.name for task in created] == ["new", "later"]
    assert [(error.name, error.error) for error in errors] == [
        ("existing", "Already exists: plans/alpha/tasks/existing.md"),
        ("../bad", "Expected a nonempty name without path separators or control characters"),
    ]
    assert service.get("alpha", "new")
    assert service.get("alpha", "later")


def test_create_batch_empty(service: TaskService, metadata: TaskMetadata) -> None:
    created, errors = service.create_batch("alpha", [], metadata)
    assert created == []
    assert errors == []


def test_create_batch_unknown_plan(service: TaskService, metadata: TaskMetadata) -> None:
    with pytest.raises(MissingDocumentError):
        service.create_batch("missing", ["a"], metadata)


def test_create_batch_reads_plan_once(
    service: TaskService, metadata: TaskMetadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan is validated once, not once per name (N+1)."""
    read = Mock(wraps=service.document_store.read)
    monkeypatch.setattr(service.document_store, "read", read)
    service.create_batch("alpha", ["one", "two", "three"], metadata)
    plan_path = service.layout.plan("alpha")
    plan_reads = [call for call in read.call_args_list if call.args[0] == plan_path]
    assert len(plan_reads) == 1


def test_patches(service: TaskService, metadata: TaskMetadata) -> None:
    service.create("alpha", "login", metadata, "Body")
    task = service.set_status("alpha", "login", "in-progress")
    assert task.document.body == "Body"
    assert task.document.metadata.status == "in-progress"
    assert task.document.get_or_derive_summary() == "Body"
    task = service.update("alpha", "login", TaskUpdate(body=""))
    assert task.document.body == ""
    assert task.document.metadata.status == "in-progress"
    assert task.document.get_or_derive_summary() is None
    assert task.document.metadata.created == metadata.created
    assert task.document.metadata.model_extra == metadata.model_extra


def test_empty_patch(
    service: TaskService, metadata: TaskMetadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = service.create("alpha", "login", metadata, "Body")
    target = service.document_store.root / task.path
    os.utime(target.path, ns=(1234567890123456789, 1234567890123456789))
    before = target.read_bytes(), target.stat().st_mtime_ns
    task = service.get("alpha", "login")
    write = Mock(side_effect=AssertionError("empty patch must not write"))
    monkeypatch.setattr(service.document_store, "write", write)
    assert service.update("alpha", "login", TaskUpdate()) == task
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    write.assert_not_called()


@pytest.mark.parametrize("plan", ["alpha", "missing"])
def test_missing_tasks_and_plans(service: TaskService, metadata: TaskMetadata, plan: str) -> None:
    for operation in (
        lambda: service.get(plan, "missing"),
        lambda: service.update(plan, "missing", TaskUpdate()),
        lambda: service.set_status(plan, "missing", "done"),
    ):
        with pytest.raises(MissingDocumentError):
            operation()
    if plan == "missing":
        # Even an orphan task cannot make a missing plan valid.
        service.document_store.create(
            service.layout.task(plan, "missing"), Document(metadata=metadata, body="")
        )
        with pytest.raises(MissingDocumentError):
            service.get(plan, "missing")
        with pytest.raises(MissingDocumentError):
            service.list(plan)
        with pytest.raises(MissingDocumentError):
            service.create(plan, "new", metadata)
        assert not (service.document_store.root / service.layout.task(plan, "new")).exists()
    else:
        assert service.list(plan) == []


@pytest.mark.parametrize(
    "name",
    ["", "/abs", "../x", "a/../x", "a/./x", "a//x", "a/", "a/ x", "a/x ", "C:/x", "a\\x", "a/\nx"],
)
def test_invalid_names(service: TaskService, metadata: TaskMetadata, name: str) -> None:
    with pytest.raises(ValidationError):
        service.layout.task("alpha", name)
    with pytest.raises(ValidationError):
        service.create("alpha", name, metadata)
    with pytest.raises(ValidationError):
        service.get("alpha", name)


@pytest.mark.parametrize(
    "patch",
    [
        {"status": "active"},
        {"status": None},
        {"body": None},
        {"created": "2026-01-01T00:00:00Z"},
        {"unknown": 1},
    ],
)
def test_patch_validation(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TaskUpdate.model_validate(patch)


def test_method_validation(service: TaskService, metadata: TaskMetadata) -> None:
    with pytest.raises(ValidationError):
        service.create("../bad", "login", metadata)
    with pytest.raises(ValidationError):
        service.create("alpha", "login", {"summary": "missing date"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.create("alpha", "login", metadata, None)  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.set_status("alpha", "login", "active")  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.list("alpha", {"limit": 0})  # pyright: ignore[reportArgumentType]


def test_nested_round_trip_and_query(service: TaskService, metadata: TaskMetadata) -> None:
    for name in ("nested/login", "other/login", "login.v2"):
        service.create("alpha", name, metadata)
    for summary in service.list("alpha"):
        task = service.get("alpha", summary.name)
        assert task.path == summary.path
        assert task.modified_at == summary.last_activity_at
        assert "body" not in summary.model_dump()
        service.set_status("alpha", summary.name, "done")
    service.update("alpha", "nested/login", TaskUpdate(body="OAuth"))
    found = service.list("alpha", TaskQuery(statuses={"done"}, search="oauth", search_body=True))
    assert [task.name for task in found] == ["nested/login"]


def test_explicit_plan_isolation(
    service: TaskService, metadata: TaskMetadata, tmp_path: Path
) -> None:
    state = ProjectStateStore(UPath(tmp_path / "state.toml"))
    state.write(ProjectState(project_name="demo"))
    plans = PlanService(service.document_store, service.layout, state)
    plans.create("beta", PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)))
    plans.set_current("alpha")
    service.create("beta", "login", metadata, "Beta")
    plans.set_current("beta")
    service.create("alpha", "login", metadata, "Alpha")
    service.update("alpha", "login", TaskUpdate(body="Alpha only"))
    service.set_status("alpha", "login", "done")
    assert service.get("beta", "login").document.body == "Beta"
    assert service.list("beta")[0].metadata.model_dump(exclude={"summary"}) == metadata.model_dump(
        exclude={"summary"}
    )
    assert service.list("alpha")[0].metadata.status == "done"
    assert state.read().current_plan == "beta"


def test_delegation(
    service: TaskService, metadata: TaskMetadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.create("alpha", "zulu", metadata)
    service.create("alpha", "alpha", metadata)
    records = service.document_store.list(
        service.layout.task_collection("alpha"), TaskMetadata, TaskQuery(descending=True)
    )
    listing = Mock(return_value=records)
    monkeypatch.setattr(service.document_store, "list", listing)
    query = TaskQuery(statuses=set(), limit=1)
    assert [item.name for item in service.list("alpha", query)] == ["zulu", "alpha"]
    listing.assert_called_once_with(service.layout.task_collection("alpha"), TaskMetadata, query)
    update = Mock()
    monkeypatch.setattr(service, "update", update)
    service.set_status("alpha", "zulu", "done")
    update.assert_called_once_with("alpha", "zulu", TaskUpdate(status="done"))
