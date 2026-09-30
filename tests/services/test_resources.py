"""One parametrized matrix over the four document resources.

The generic machinery lives in :class:`~machinate.services.document.DocumentService`;
these tests drive each resource through its public service methods, with a small adapter
per resource for the argument differences (plan-scoped or not, status or not). Plan
selection/activity and the project overview have their own tests.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from machinate.models.documents import (
    DocumentRecord,
    LoadedDocument,
    LoadedPlan,
    Metadata,
    ParsedDocument,
    PlanStatus,
    Tag,
    TaskStatus,
)
from machinate.models.operations import (
    BatchCreated,
    CreateInput,
    DocumentQuery,
    DocumentUpdate,
    PlanQuery,
    StatusCreateInput,
    StatusUpdate,
    TaskQuery,
)
from machinate.services.context import ContextService
from machinate.services.doc import DocService
from machinate.services.errors import ExistsError, NotFoundError
from machinate.services.plan import PlanService
from machinate.services.task import TaskService
from machinate.storage import (
    DocumentStore,
    Layout,
    ProjectState,
    ProjectStateStore,
)


def _flat_record[M: Metadata](record: DocumentRecord[M]) -> DocumentRecord[Metadata]:
    return DocumentRecord[Metadata](
        name=record.name,
        path=record.path,
        metadata=record.metadata,
        modified_at=record.modified_at,
        summary=record.summary,
    )


def _flat_loaded[M: Metadata](loaded: LoadedDocument[M] | LoadedPlan) -> LoadedDocument[Metadata]:
    record = loaded.record
    return LoadedDocument[Metadata](
        record=DocumentRecord[Metadata](
            name=record.name,
            path=record.path,
            metadata=record.metadata,
            modified_at=record.modified_at,
            summary=record.summary,
        ),
        body=loaded.body,
    )


def _provided(**values: object) -> dict[str, object]:
    """Only the update fields actually supplied; an unset field stays unset."""
    return {key: value for key, value in values.items() if value is not None}


@dataclass(frozen=True)
class ResourceAdapter:
    """Public-method operations for one resource, with the plan/status differences folded in."""

    kind: str
    name: str
    is_plan_scoped: bool
    document_store: DocumentStore
    ensure_parent: Callable[[], None]
    create: Callable[..., LoadedDocument[Metadata]]
    create_many: Callable[..., BatchCreated[LoadedDocument[Metadata]]]
    get: Callable[[str], LoadedDocument[Metadata]]
    info: Callable[[str], DocumentRecord[Metadata]]
    update: Callable[..., LoadedDocument[Metadata]]
    list_records: Callable[..., list[DocumentRecord[Metadata]]]
    path: Callable[[str], PurePosixPath]
    query_type: Callable[..., DocumentQuery]
    write_body: Callable[[str, str], None]
    count: Callable[[], int] | None
    status_default: str | None
    changed_status: str | None


def _plan_adapter(plans: PlanService) -> ResourceAdapter:
    def create(
        name: str,
        *,
        summary: str | None = None,
        tags: list[Tag] | None = None,
        status: PlanStatus | None = None,
    ) -> LoadedDocument[Metadata]:
        return _flat_loaded(
            plans.create(
                name,
                StatusCreateInput[PlanStatus](summary=summary, tags=tags or [], status=status),
            )
        )

    def create_many(
        names: list[str], *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> BatchCreated[LoadedDocument[Metadata]]:
        batch = plans.create_many(
            names, StatusCreateInput[PlanStatus](summary=summary, tags=tags or [])
        )
        return BatchCreated(
            created=[_flat_loaded(loaded) for loaded in batch.created], failures=batch.failures
        )

    def get(name: str) -> LoadedDocument[Metadata]:
        return _flat_loaded(plans.get(name))

    def update(
        name: str,
        *,
        summary: str | None = None,
        tags: list[Tag] | None = None,
        status: PlanStatus | None = None,
    ) -> LoadedDocument[Metadata]:
        changes = _provided(summary=summary, tags=tags, status=status)
        return _flat_loaded(plans.update(name, StatusUpdate[PlanStatus].model_validate(changes)))

    def list_records(query: PlanQuery | None = None) -> list[DocumentRecord[Metadata]]:
        return [_flat_record(record) for record in plans.list_records(query)]

    def write_body(name: str, body: str) -> None:
        loaded = plans.get(name)
        plans.document_store.write(
            loaded.record.path, ParsedDocument(metadata=loaded.record.metadata, body=body)
        )

    def ensure_parent() -> None:
        return None

    return ResourceAdapter(
        kind="plan",
        name="item",
        is_plan_scoped=False,
        document_store=plans.document_store,
        ensure_parent=ensure_parent,
        create=create,
        create_many=create_many,
        get=get,
        info=lambda name: _flat_record(plans.get_info(name)),
        update=update,
        list_records=list_records,
        path=plans.get_path,
        query_type=PlanQuery,
        write_body=write_body,
        count=None,
        status_default="draft",
        changed_status="active",
    )


def _task_adapter(tasks: TaskService, plans: PlanService) -> ResourceAdapter:
    def create(
        name: str,
        *,
        summary: str | None = None,
        tags: list[Tag] | None = None,
        status: TaskStatus | None = None,
    ) -> LoadedDocument[Metadata]:
        return _flat_loaded(
            tasks.create(
                "alpha",
                name,
                StatusCreateInput[TaskStatus](summary=summary, tags=tags or [], status=status),
            )
        )

    def create_many(
        names: list[str], *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> BatchCreated[LoadedDocument[Metadata]]:
        batch = tasks.create_many(
            "alpha", names, StatusCreateInput[TaskStatus](summary=summary, tags=tags or [])
        )
        return BatchCreated(
            created=[_flat_loaded(loaded) for loaded in batch.created], failures=batch.failures
        )

    def get(name: str) -> LoadedDocument[Metadata]:
        return _flat_loaded(tasks.get("alpha", name))

    def update(
        name: str,
        *,
        summary: str | None = None,
        tags: list[Tag] | None = None,
        status: TaskStatus | None = None,
    ) -> LoadedDocument[Metadata]:
        changes = _provided(summary=summary, tags=tags, status=status)
        return _flat_loaded(
            tasks.update("alpha", name, StatusUpdate[TaskStatus].model_validate(changes))
        )

    def list_records(
        query: TaskQuery | None = None, *, plan: str = "alpha"
    ) -> list[DocumentRecord[Metadata]]:
        return [_flat_record(record) for record in tasks.list_records(plan, query)]

    def write_body(name: str, body: str) -> None:
        loaded = tasks.get("alpha", name)
        tasks.document_store.write(
            loaded.record.path, ParsedDocument(metadata=loaded.record.metadata, body=body)
        )

    def ensure_parent() -> None:
        plans.create("alpha", StatusCreateInput[PlanStatus]())

    return ResourceAdapter(
        kind="task",
        name="topic/item",
        is_plan_scoped=True,
        document_store=tasks.document_store,
        ensure_parent=ensure_parent,
        create=create,
        create_many=create_many,
        get=get,
        info=lambda name: _flat_record(tasks.get_info("alpha", name)),
        update=update,
        list_records=list_records,
        path=lambda name: tasks.get_path("alpha", name),
        query_type=TaskQuery,
        write_body=write_body,
        count=None,
        status_default="todo",
        changed_status="in-progress",
    )


def _context_adapter(contexts: ContextService, plans: PlanService) -> ResourceAdapter:
    def create(
        name: str, *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> LoadedDocument[Metadata]:
        return _flat_loaded(
            contexts.create("alpha", name, CreateInput(summary=summary, tags=tags or []))
        )

    def create_many(
        names: list[str], *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> BatchCreated[LoadedDocument[Metadata]]:
        batch = contexts.create_many("alpha", names, CreateInput(summary=summary, tags=tags or []))
        return BatchCreated(
            created=[_flat_loaded(loaded) for loaded in batch.created], failures=batch.failures
        )

    def get(name: str) -> LoadedDocument[Metadata]:
        return _flat_loaded(contexts.get("alpha", name))

    def update(
        name: str, *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> LoadedDocument[Metadata]:
        changes = _provided(summary=summary, tags=tags)
        return _flat_loaded(contexts.update("alpha", name, DocumentUpdate.model_validate(changes)))

    def list_records(
        query: DocumentQuery | None = None, *, plan: str = "alpha"
    ) -> list[DocumentRecord[Metadata]]:
        return [_flat_record(record) for record in contexts.list_records(plan, query)]

    def write_body(name: str, body: str) -> None:
        loaded = contexts.get("alpha", name)
        contexts.document_store.write(
            loaded.record.path, ParsedDocument(metadata=loaded.record.metadata, body=body)
        )

    def ensure_parent() -> None:
        plans.create("alpha", StatusCreateInput[PlanStatus]())

    return ResourceAdapter(
        kind="context",
        name="topic/item",
        is_plan_scoped=True,
        document_store=contexts.document_store,
        ensure_parent=ensure_parent,
        create=create,
        create_many=create_many,
        get=get,
        info=lambda name: _flat_record(contexts.get_info("alpha", name)),
        update=update,
        list_records=list_records,
        path=lambda name: contexts.get_path("alpha", name),
        query_type=DocumentQuery,
        write_body=write_body,
        count=lambda: contexts.count_documents("alpha"),
        status_default=None,
        changed_status=None,
    )


def _doc_adapter(docs: DocService) -> ResourceAdapter:
    def create(
        name: str, *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> LoadedDocument[Metadata]:
        return _flat_loaded(docs.create(name, CreateInput(summary=summary, tags=tags or [])))

    def create_many(
        names: list[str], *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> BatchCreated[LoadedDocument[Metadata]]:
        batch = docs.create_many(names, CreateInput(summary=summary, tags=tags or []))
        return BatchCreated(
            created=[_flat_loaded(loaded) for loaded in batch.created], failures=batch.failures
        )

    def get(name: str) -> LoadedDocument[Metadata]:
        return _flat_loaded(docs.get(name))

    def update(
        name: str, *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> LoadedDocument[Metadata]:
        changes = _provided(summary=summary, tags=tags)
        return _flat_loaded(docs.update(name, DocumentUpdate.model_validate(changes)))

    def list_records(query: DocumentQuery | None = None) -> list[DocumentRecord[Metadata]]:
        return [_flat_record(record) for record in docs.list_records(query)]

    def write_body(name: str, body: str) -> None:
        loaded = docs.get(name)
        docs.document_store.write(
            loaded.record.path, ParsedDocument(metadata=loaded.record.metadata, body=body)
        )

    def ensure_parent() -> None:
        return None

    return ResourceAdapter(
        kind="doc",
        name="topic/item",
        is_plan_scoped=False,
        document_store=docs.document_store,
        ensure_parent=ensure_parent,
        create=create,
        create_many=create_many,
        get=get,
        info=lambda name: _flat_record(docs.get_info(name)),
        update=update,
        list_records=list_records,
        path=docs.get_path,
        query_type=DocumentQuery,
        write_body=write_body,
        count=docs.count_documents,
        status_default=None,
        changed_status=None,
    )


@pytest.fixture
def adapter(tmp_path: Path, request: pytest.FixtureRequest) -> ResourceAdapter:
    layout = Layout()
    store = DocumentStore(tmp_path / "docs")
    state = ProjectStateStore(tmp_path / "state.toml")
    state.write(ProjectState(project_name="demo"))
    plans = PlanService(store, layout, state)
    kind = cast("str", request.param)
    match kind:
        case "plan":
            return _plan_adapter(plans)
        case "task":
            return _task_adapter(TaskService(store, layout), plans)
        case "context":
            return _context_adapter(ContextService(store, layout), plans)
        case "doc":
            return _doc_adapter(DocService(store, layout))
        case _:
            msg = f"unknown resource kind {kind!r}"
            raise AssertionError(msg)


ADAPTER_CASES = pytest.mark.parametrize(
    "adapter", ["plan", "task", "context", "doc"], indirect=True
)

COUNT_CASES = pytest.mark.parametrize("adapter", ["context", "doc"], indirect=True)


@ADAPTER_CASES
def test_create_get_path_duplicate_and_suffix(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    created = adapter.create(adapter.name, summary="S", tags=["x"])
    assert created.record.name == adapter.name
    assert created.record.metadata.summary == "S"
    assert created.record.metadata.tags == ["x"]
    assert created.record.metadata.created_at.tzinfo is not None
    assert created.record.path == adapter.path(adapter.name)
    if adapter.status_default is not None:
        status = cast("str", json.loads(created.record.metadata.model_dump_json())["status"])
        assert status == adapter.status_default

    suffixed_name = "suffixed"
    parent, _, _ = adapter.name.rpartition("/")
    suffixed_input = f"{parent}/{suffixed_name}.md" if parent else f"{suffixed_name}.md"
    suffixed = adapter.create(suffixed_input)
    expected_suffixed = f"{parent}/{suffixed_name}" if parent else suffixed_name
    assert suffixed.record.name == expected_suffixed
    assert suffixed.record.path == adapter.path(expected_suffixed)

    adapter.write_body(adapter.name, "Body\n")
    loaded = adapter.get(adapter.name)
    assert loaded.body == "Body\n"
    assert loaded == adapter.get(adapter.name)
    with pytest.raises(ExistsError):
        adapter.create(adapter.name)


@ADAPTER_CASES
def test_create_many(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    batch = adapter.create_many(["one", "two"])
    assert [loaded.record.name for loaded in batch.created] == ["one", "two"]
    assert batch.failures == []


@ADAPTER_CASES
def test_list_filters_sorts_and_limits(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    for name, tags in (("b", ["x"]), ("a", ["y"]), ("c", ["x"])):
        adapter.create(name, tags=tags)

    tagged = adapter.list_records(adapter.query_type(tags={"x"}))
    assert [record.name for record in tagged] == ["b", "c"]
    descending = adapter.list_records(adapter.query_type(descending=True))
    assert [record.name for record in descending] == ["c", "b", "a"]
    limited = adapter.list_records(adapter.query_type(limit=2))
    assert [record.name for record in limited] == ["a", "b"]


@ADAPTER_CASES
def test_info_matches_record_without_body(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    adapter.create(adapter.name)
    info = adapter.info(adapter.name)
    assert info == adapter.get(adapter.name).record
    assert "body" not in info.model_dump()


@ADAPTER_CASES
def test_update_applies_and_empty_update_never_writes(
    adapter: ResourceAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter.ensure_parent()
    created = adapter.create(adapter.name)
    adapter.write_body(adapter.name, "Body")

    if adapter.changed_status is not None:
        updated = adapter.update(adapter.name, status=adapter.changed_status)
        status = cast("str", json.loads(updated.record.metadata.model_dump_json())["status"])
        assert status == adapter.changed_status
    else:
        updated = adapter.update(adapter.name, summary="new", tags=["t"])
        assert updated.record.metadata.summary == "new"
        assert updated.record.metadata.tags == ["t"]
    assert updated.body == "Body"

    target = adapter.document_store.root / created.record.path
    before = target.read_bytes(), target.stat().st_mtime_ns
    write = Mock(side_effect=AssertionError("empty patch must not write"))
    monkeypatch.setattr(adapter.document_store, "write", write)
    adapter.update(adapter.name)
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    write.assert_not_called()


@ADAPTER_CASES
def test_missing_operations(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    with pytest.raises(NotFoundError):
        adapter.get("missing")
    with pytest.raises(NotFoundError):
        adapter.info("missing")
    with pytest.raises(NotFoundError):
        adapter.update("missing")
    if adapter.is_plan_scoped:
        with pytest.raises(NotFoundError):
            adapter.list_records(plan="missing")


@ADAPTER_CASES
@pytest.mark.parametrize(
    "name", ["", "/abs", "../x", "a/../x", "a//x", "a/ x", "a/x ", "C:/x", "a\\x"]
)
def test_invalid_names(adapter: ResourceAdapter, name: str) -> None:
    adapter.ensure_parent()
    with pytest.raises(ValidationError):
        adapter.create(name)
    with pytest.raises(ValidationError):
        adapter.get(name)


@COUNT_CASES
def test_count_documents_matches_list(adapter: ResourceAdapter) -> None:
    count = adapter.count
    assert count is not None
    adapter.ensure_parent()
    for name in ("one", "two/nested"):
        adapter.create(name)
    assert count() == len(adapter.list_records()) == 2


def test_concrete_services_are_thin_instances(tmp_path: Path) -> None:
    """The public resource methods bind the same collection and paths."""
    layout = Layout()
    store = DocumentStore(tmp_path / "docs")
    state = ProjectStateStore(tmp_path / "state.toml")
    state.write(ProjectState(project_name="demo"))
    plans = PlanService(store, layout, state)
    tasks = TaskService(store, layout)
    contexts = ContextService(store, layout)
    docs = DocService(store, layout)
    plans.create("alpha", StatusCreateInput[PlanStatus]())

    assert plans.create("p.md", StatusCreateInput[PlanStatus]()).record.path == PurePosixPath(
        "plans/p/plan.md"
    )
    assert tasks.create("alpha", "t.md", StatusCreateInput[TaskStatus]()).record.path == (
        PurePosixPath("plans/alpha/tasks/t.md")
    )
    assert contexts.create("alpha", "c.md", CreateInput()).record.path == PurePosixPath(
        "plans/alpha/context/c.md"
    )
    assert docs.create("d.md", CreateInput()).record.path == PurePosixPath("docs/d.md")
    assert contexts.count_documents("alpha") == 1
    assert docs.count_documents() == 1
