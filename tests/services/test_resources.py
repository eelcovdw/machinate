"""One parametrized matrix over the four document resources.

The generic machinery lives in :class:`~machinate.services.document.DocumentService`;
these tests drive each resource through its public service methods, with a small adapter
per resource for the argument differences (plan-scoped or not, status or not). Plan
selection/activity and the project overview have their own tests.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

import pytest
from pydantic import ValidationError

from machinate.models.documents import (
    DocumentRecord,
    LoadedDocument,
    LoadedPlan,
    Metadata,
    ParsedDocument,
    PlanRecord,
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
    atomic,
)
from machinate.storage import document_store as document_store_module


def _flat_record[M: Metadata](
    record: DocumentRecord[M] | PlanRecord,
) -> DocumentRecord[Metadata]:
    return DocumentRecord[Metadata](
        name=record.name,
        path=record.path,
        metadata=record.metadata,
        modified_at=record.modified_at,
        summary=record.summary,
    )


def _flat_loaded[M: Metadata](loaded: LoadedDocument[M] | LoadedPlan) -> LoadedDocument[Metadata]:
    return LoadedDocument[Metadata](record=_flat_record(loaded.record), body=loaded.body)


def _flat_batch[M: Metadata](
    batch: BatchCreated[DocumentRecord[M]],
) -> BatchCreated[DocumentRecord[Metadata]]:
    return BatchCreated(
        created=[_flat_record(record) for record in batch.created], failures=batch.failures
    )


def _provided(**values: object) -> dict[str, object]:
    """Only the update fields actually supplied; an unset field stays unset."""
    return {key: value for key, value in values.items() if value is not None}


def _status(metadata: Metadata) -> str | None:
    return cast("str | None", getattr(metadata, "status", None))


@dataclass(frozen=True)
class ResourceAdapter:
    """Public-method operations for one resource, with the plan/status differences folded in."""

    kind: str
    name: str
    is_plan_scoped: bool
    document_store: DocumentStore
    ensure_parent: Callable[[], None]
    create: Callable[..., LoadedDocument[Metadata]]
    create_many: Callable[..., BatchCreated[DocumentRecord[Metadata]]] | None
    get: Callable[[str], LoadedDocument[Metadata]]
    info: Callable[[str], DocumentRecord[Metadata]]
    update: Callable[..., LoadedDocument[Metadata]]
    list_records: Callable[..., list[DocumentRecord[Metadata]]]
    expected_path: Callable[[str], PurePosixPath]
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
        create_many=None,
        get=get,
        info=lambda name: _flat_record(plans.get_record(name)),
        update=update,
        list_records=list_records,
        expected_path=lambda name: PurePosixPath("plans", name, "plan.md"),
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
        batch = tasks.create_many(
            "alpha",
            [name],
            StatusCreateInput[TaskStatus](summary=summary, tags=tags or [], status=status),
        )
        return _flat_loaded(LoadedDocument(record=batch.created[0], body=""))

    def create_many(
        names: list[str], *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> BatchCreated[DocumentRecord[Metadata]]:
        return _flat_batch(
            tasks.create_many(
                "alpha", names, StatusCreateInput[TaskStatus](summary=summary, tags=tags or [])
            )
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
        info=lambda name: _flat_record(tasks.get_record("alpha", name)),
        update=update,
        list_records=list_records,
        expected_path=lambda name: PurePosixPath("plans/alpha/tasks", f"{name}.md"),
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
        batch = contexts.create_many("alpha", [name], CreateInput(summary=summary, tags=tags or []))
        return _flat_loaded(LoadedDocument(record=batch.created[0], body=""))

    def create_many(
        names: list[str], *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> BatchCreated[DocumentRecord[Metadata]]:
        return _flat_batch(
            contexts.create_many("alpha", names, CreateInput(summary=summary, tags=tags or []))
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
        info=lambda name: _flat_record(contexts.get_record("alpha", name)),
        update=update,
        list_records=list_records,
        expected_path=lambda name: PurePosixPath("plans/alpha/context", f"{name}.md"),
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
        batch = docs.create_many([name], CreateInput(summary=summary, tags=tags or []))
        return _flat_loaded(LoadedDocument(record=batch.created[0], body=""))

    def create_many(
        names: list[str], *, summary: str | None = None, tags: list[Tag] | None = None
    ) -> BatchCreated[DocumentRecord[Metadata]]:
        return _flat_batch(docs.create_many(names, CreateInput(summary=summary, tags=tags or [])))

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
        info=lambda name: _flat_record(docs.get_record(name)),
        update=update,
        list_records=list_records,
        expected_path=lambda name: PurePosixPath("docs", f"{name}.md"),
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
BATCH_CASES = pytest.mark.parametrize("adapter", ["task", "context", "doc"], indirect=True)
COUNT_CASES = pytest.mark.parametrize("adapter", ["context", "doc"], indirect=True)


@ADAPTER_CASES
def test_create_get_path_duplicate_and_suffix(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    created = adapter.create(adapter.name, summary="S", tags=["x"])
    assert created.record.name == adapter.name
    assert created.record.metadata.summary == "S"
    assert created.record.metadata.tags == ["x"]
    assert created.record.metadata.created_at.tzinfo is not None
    assert created.record.path == adapter.expected_path(adapter.name)
    if adapter.status_default is not None:
        assert _status(created.record.metadata) == adapter.status_default

    suffixed_name = "suffixed"
    parent, _, _ = adapter.name.rpartition("/")
    suffixed_input = f"{parent}/{suffixed_name}.md" if parent else f"{suffixed_name}.md"
    suffixed = adapter.create(suffixed_input)
    expected_suffixed = f"{parent}/{suffixed_name}" if parent else suffixed_name
    assert suffixed.record.name == expected_suffixed
    assert suffixed.record.path == adapter.expected_path(expected_suffixed)

    adapter.write_body(adapter.name, "Body\n")
    loaded = adapter.get(adapter.name)
    assert loaded.body == "Body\n"
    assert loaded == adapter.get(adapter.name)
    create_many = adapter.create_many
    if create_many is None:
        with pytest.raises(ExistsError):
            adapter.create(adapter.name)
    else:
        assert create_many([adapter.name]).failures[0].reason == "exists"


@BATCH_CASES
def test_create_many(adapter: ResourceAdapter, monkeypatch: pytest.MonkeyPatch) -> None:
    create_many = adapter.create_many
    assert create_many is not None
    adapter.ensure_parent()
    batch = create_many(["one", "two"])
    assert [record.name for record in batch.created] == ["one", "two"]
    assert batch.failures == []

    adapter.create("existing")
    partial = create_many(["new", "existing", "../bad", "later"])
    assert [record.name for record in partial.created] == ["new", "later"]
    assert [failure.name for failure in partial.failures] == ["existing", "../bad"]
    assert [failure.reason for failure in partial.failures] == ["exists", "invalid_name"]

    blocked_path = adapter.document_store.root / adapter.expected_path("blocked")

    def deny(target: Path, content: bytes) -> None:
        if target == blocked_path:
            raise PermissionError("denied")
        atomic.atomic_create(target, content)

    monkeypatch.setattr(document_store_module, "atomic_create", deny)
    failed = create_many(["blocked", "after"])
    assert len(failed.created) == 1
    assert [failure.reason for failure in failed.failures] == ["failed"]


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


@ADAPTER_CASES
def test_update_applies_and_empty_update_never_writes(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    created = adapter.create(adapter.name)
    adapter.write_body(adapter.name, "Body")

    if adapter.changed_status is not None:
        updated = adapter.update(adapter.name, status=adapter.changed_status)
        assert _status(updated.record.metadata) == adapter.changed_status
    else:
        updated = adapter.update(adapter.name, summary="new", tags=["t"])
        assert updated.record.metadata.summary == "new"
        assert updated.record.metadata.tags == ["t"]
    assert updated.body == "Body"

    target = adapter.document_store.root / created.record.path
    before = target.read_bytes(), target.stat().st_mtime_ns
    adapter.update(adapter.name)
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before


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
def test_invalid_names(adapter: ResourceAdapter) -> None:
    adapter.ensure_parent()
    with pytest.raises(ValidationError):
        adapter.get("../x")
    create_many = adapter.create_many
    if create_many is None:
        with pytest.raises(ValidationError):
            adapter.create("../x")
    else:
        assert create_many(["../x"]).failures[0].reason == "invalid_name"


@COUNT_CASES
def test_count_documents_matches_list(adapter: ResourceAdapter) -> None:
    count = adapter.count
    assert count is not None
    adapter.ensure_parent()
    for name in ("one", "two/nested"):
        adapter.create(name)
    assert count() == len(adapter.list_records()) == 2
