import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError
from upath import UPath

from machinate.storage import (
    DateTimeRange,
    Document,
    DocumentCollection,
    DocumentQuery,
    DocumentStore,
    InvalidDocumentError,
    Layout,
    PlanMetadata,
    PlanQuery,
    StorageError,
    TaskMetadata,
    TaskQuery,
)


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    store = DocumentStore(UPath(tmp_path))
    for name, day, status, summary, body, stamp in [
        ("alpha", 1, "active", "OAuth", "", 100),
        ("beta", 2, "draft", "Other", "OAuth body", 200),
        ("gamma", 2, "done", "OAuth", "", 200),
    ]:
        path = Layout().plan(name)
        store.create(
            path,
            Document(
                metadata=PlanMetadata.model_validate(
                    {
                        "created": datetime(2026, 9, day, tzinfo=UTC),
                        "status": status,
                        "summary": summary,
                    }
                ),
                body=body,
            ),
        )
        os.utime(tmp_path / path, (stamp, stamp))
    return store


def names(store: DocumentStore, query: PlanQuery) -> list[str]:
    return [record.name for record in store.list(Layout().plan_collection(), PlanMetadata, query)]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (PlanQuery(), ["alpha", "beta", "gamma"]),
        (PlanQuery(created_range=DateTimeRange()), ["alpha", "beta", "gamma"]),
        (
            PlanQuery(created_range=DateTimeRange(gte=datetime(2026, 9, 2, tzinfo=UTC))),
            ["beta", "gamma"],
        ),
        (PlanQuery(created_range=DateTimeRange(lte=datetime(2026, 9, 1, tzinfo=UTC))), ["alpha"]),
        (PlanQuery(search=""), ["alpha", "beta", "gamma"]),
        (PlanQuery(search="ALP"), ["alpha"]),
        (PlanQuery(search="oAuTh"), ["alpha", "gamma"]),
        (PlanQuery(search="oauth", search_body=True), ["alpha", "beta", "gamma"]),
        (PlanQuery(statuses=set()), []),
        (PlanQuery(statuses={"active", "done"}), ["alpha", "gamma"]),
        (
            PlanQuery(
                created_range=DateTimeRange(
                    gte=datetime(2026, 9, 2, tzinfo=UTC), lte=datetime(2026, 9, 2, tzinfo=UTC)
                )
            ),
            ["beta", "gamma"],
        ),
        (
            PlanQuery(updated_range=DateTimeRange(gte=datetime.fromtimestamp(200, UTC))),
            ["beta", "gamma"],
        ),
        (PlanQuery(updated_range=DateTimeRange(gte=datetime.fromtimestamp(201, UTC))), []),
        (PlanQuery(sort="name", descending=True, limit=2), ["gamma", "beta"]),
        (PlanQuery(sort="created", descending=True), ["beta", "gamma", "alpha"]),
        (PlanQuery(sort="updated", descending=True), ["beta", "gamma", "alpha"]),
        (PlanQuery(sort="created"), ["alpha", "beta", "gamma"]),
        (PlanQuery(sort="updated"), ["alpha", "beta", "gamma"]),
        (
            PlanQuery(
                search="oauth",
                statuses={"draft", "done"},
                created_range=DateTimeRange(
                    gte=datetime(2026, 9, 2, tzinfo=UTC), lte=datetime(2026, 9, 2, tzinfo=UTC)
                ),
                updated_range=DateTimeRange(gte=datetime.fromtimestamp(200, UTC)),
                sort="updated",
                descending=True,
                limit=1,
            ),
            ["gamma"],
        ),
    ],
)
def test_query_mechanics(store: DocumentStore, query: PlanQuery, expected: list[str]) -> None:
    assert names(store, query) == expected


@pytest.mark.parametrize(
    "data",
    [
        {"created_range": {"gte": "2026-09-02T00:00:00Z", "lte": "2026-09-01T00:00:00Z"}},
        {"updated_range": {"gte": "2026-09-01T12:00:00"}},
        {"created_range": {"gte": "invalid"}},
        {"created_range": {"gt": "2026-09-01T00:00:00Z"}},
        {"limit": 0},
        {"limit": -1},
        {"statuses": ["invalid"]},
        {"sort": "invalid"},
    ],
)
def test_query_validation(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PlanQuery.model_validate(data)


@pytest.mark.parametrize("folder", ["tasks", "context"])
def test_activity_precedes_filters_sort_and_limit(
    store: DocumentStore, tmp_path: Path, folder: str
) -> None:
    child = tmp_path / "alpha" / folder / "nested" / "bad.md"
    child.parent.mkdir(parents=True)
    child.write_text("deliberately invalid document")
    os.utime(child, (300, 300))
    unrelated = child.with_suffix(".txt")
    unrelated.write_text("unrelated")
    os.utime(unrelated, (900, 900))
    outside = tmp_path / "alpha" / "unrelated.md"
    outside.write_text("also outside activity scopes")
    os.utime(outside, (900, 900))
    query = PlanQuery(
        updated_range=DateTimeRange(gte=datetime.fromtimestamp(300, UTC)),
        sort="updated",
        descending=True,
        limit=1,
    )
    records = store.list(Layout().plan_collection(), PlanMetadata, query)
    assert [record.name for record in records] == ["alpha"]
    assert records[0].last_activity_at == datetime.fromtimestamp(300, UTC)
    assert names(store, PlanQuery(sort="updated", descending=True, limit=1)) == ["alpha"]
    assert (
        names(store, PlanQuery(updated_range=DateTimeRange(gte=datetime.fromtimestamp(301, UTC))))
        == []
    )


def test_discovery_empty_scopes_and_malformed_documents(
    store: DocumentStore, tmp_path: Path
) -> None:
    assert store.list(Layout().task_collection("alpha"), TaskMetadata) == []
    (tmp_path / "alpha" / "tasks").mkdir()
    assert store.list(Layout().task_collection("alpha"), TaskMetadata) == []
    (tmp_path / "alpha" / "tasks" / "ignored.txt").write_text("invalid")
    (tmp_path / "alpha" / "tasks" / "directory.md").mkdir()
    assert store.list(Layout().task_collection("alpha"), TaskMetadata) == []
    bad = tmp_path / "alpha" / "tasks" / "nested" / "bad.md"
    bad.parent.mkdir()
    bad.write_text("invalid")
    with pytest.raises(InvalidDocumentError) as error:
        store.list(Layout().task_collection("alpha"), TaskMetadata)
    assert error.value.path == PurePosixPath("alpha/tasks/nested/bad.md")
    (tmp_path / "alpha" / "plan.md").write_text("invalid")
    with pytest.raises(InvalidDocumentError):
        store.list(Layout().plan_collection(), PlanMetadata)


def test_non_directory_collection_is_error(store: DocumentStore) -> None:
    with pytest.raises(StorageError):
        store.list(
            DocumentCollection(path=PurePosixPath("alpha/plan.md"), pattern=PurePosixPath("*.md")),
            PlanMetadata,
        )


def test_missing_root_is_empty(tmp_path: Path) -> None:
    assert (
        DocumentStore(UPath(tmp_path / "absent")).list(Layout().plan_collection(), PlanMetadata)
        == []
    )


def test_summary_has_no_body(store: DocumentStore) -> None:
    record = store.list(Layout().plan_collection(), PlanMetadata, DocumentQuery(limit=1))[0]
    assert record.path == PurePosixPath("alpha/plan.md")
    assert '"body"' not in record.model_dump_json()


@pytest.mark.parametrize("query_type", [DocumentQuery, PlanQuery, TaskQuery])
def test_unknown_query_fields_are_rejected(query_type: type[DocumentQuery]) -> None:
    with pytest.raises(ValidationError) as error:
        query_type.model_validate({"status": ["done"]})
    assert error.value.errors()[0]["type"] == "extra_forbidden"
    assert error.value.errors()[0]["loc"] == ("status",)


@pytest.mark.parametrize("folder", ["tasks", "context"])
def test_nested_document_names_support_search_and_ordering(
    store: DocumentStore, tmp_path: Path, folder: str
) -> None:
    collection = DocumentCollection(
        path=PurePosixPath("alpha", folder), pattern=PurePosixPath("**/*.md")
    )
    for name in ("two/login", "one/login", "login.v2"):
        path = collection.path / f"{name}.md"
        store.create(
            path,
            Document(metadata=TaskMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body=""),
        )
        os.utime(tmp_path / path, (100, 100))

    for query in (
        DocumentQuery(),
        DocumentQuery(sort="created", descending=True),
        DocumentQuery(sort="updated", descending=True),
    ):
        records = store.list(collection, TaskMetadata, query)
        assert [record.name for record in records] == ["login.v2", "one/login", "two/login"]

    records = store.list(collection, TaskMetadata, DocumentQuery(search="ONE/LOGIN"))
    assert [record.name for record in records] == ["one/login"]
    assert records[0].path == collection.path / "one/login.md"
    records = store.list(collection, TaskMetadata, DocumentQuery(descending=True, limit=1))
    assert [record.name for record in records] == ["two/login"]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (TaskQuery(), ["alpha", "beta", "nested/gamma"]),
        (TaskQuery(statuses=set()), []),
        (TaskQuery(statuses={"todo"}), ["alpha"]),
        (TaskQuery(statuses={"in-progress"}), ["beta"]),
        (TaskQuery(statuses={"done"}), ["nested/gamma"]),
        (TaskQuery(statuses={"todo", "in-progress"}), ["alpha", "beta"]),
        (
            TaskQuery(
                statuses={"in-progress", "done"},
                search="oauth",
                search_body=True,
                created_range=DateTimeRange(
                    gte=datetime(2026, 9, 2, tzinfo=UTC), lte=datetime(2026, 9, 2, tzinfo=UTC)
                ),
                updated_range=DateTimeRange(gte=datetime.fromtimestamp(200, UTC)),
                sort="updated",
                descending=True,
                limit=1,
            ),
            ["beta"],
        ),
    ],
)
def test_task_status_queries(store: DocumentStore, query: TaskQuery, expected: list[str]) -> None:
    for name, status, day, summary, body, stamp in [
        ("alpha", "todo", 1, "OAuth", "", 100),
        ("beta", "in-progress", 2, None, "OAuth body", 200),
        ("nested/gamma", "done", 2, "OAuth", "", 200),
    ]:
        path = Layout().task("alpha", name)
        store.create(
            path,
            Document(
                metadata=TaskMetadata.model_validate(
                    {
                        "created": datetime(2026, 9, day, tzinfo=UTC),
                        "status": status,
                        "summary": summary,
                    }
                ),
                body=body,
            ),
        )
        os.utime((store.root / path).path, (stamp, stamp))
    records = store.list(Layout().task_collection("alpha"), TaskMetadata, query)
    assert [record.name for record in records] == expected


@pytest.mark.parametrize("status", ["draft", "active", "invalid", None])
def test_task_query_rejects_invalid_statuses(status: str | None) -> None:
    with pytest.raises(ValidationError):
        TaskQuery.model_validate({"statuses": [status]})


def test_date_range_json_round_trip() -> None:
    query = TaskQuery.model_validate(
        {"created_range": {"gte": "2026-09-01T00:00:00Z", "lte": "2026-09-02T00:00:00Z"}}
    )
    assert query.created_range == DateTimeRange(
        gte=datetime(2026, 9, 1, tzinfo=UTC), lte=datetime(2026, 9, 2, tzinfo=UTC)
    )
    assert TaskQuery.model_validate_json(query.model_dump_json()) == query


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ({}, ["alpha", "beta", "gamma"]),
        ({"lte": "1970-01-01T00:03:20Z"}, ["alpha", "beta", "gamma"]),
        ({"lte": "1970-01-01T00:03:19Z"}, ["alpha"]),
        ({"gte": "1970-01-01T00:03:20Z", "lte": "1970-01-01T00:03:20Z"}, ["beta", "gamma"]),
        ({"gte": "1970-01-01T01:03:20+01:00", "lte": "1970-01-01T00:03:20Z"}, ["beta", "gamma"]),
    ],
)
def test_updated_range(store: DocumentStore, bounds: dict[str, str], expected: list[str]) -> None:
    query = PlanQuery.model_validate({"updated_range": bounds})
    assert names(store, query) == expected
    assert PlanQuery.model_validate_json(query.model_dump_json()) == query


@pytest.mark.parametrize(
    "bounds",
    [
        {"gte": "2026-09-01T12:00:00"},
        {"lte": "2026-09-01T12:00:00"},
        {"gte": "2026-09-02T12:00:00Z", "lte": "2026-09-01T12:00:00Z"},
        {"lte": "invalid"},
        {"lt": "2026-09-01T12:00:00Z"},
    ],
)
def test_updated_range_validation(bounds: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        DateTimeRange.model_validate(bounds)


def test_updated_upper_bound_uses_recursive_activity(store: DocumentStore) -> None:
    path = Layout().task("alpha", "nested/task")
    store.create(
        path, Document(metadata=TaskMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body="")
    )
    os.utime((store.root / path).path, (300, 300))
    assert names(
        store,
        PlanQuery(
            updated_range=DateTimeRange(lte=datetime.fromtimestamp(200, UTC)),
            sort="updated",
            descending=True,
            limit=1,
        ),
    ) == ["beta"]


@pytest.mark.parametrize("field", ["created_range", "updated_range"])
@pytest.mark.parametrize("bound", ["gte", "lte"])
def test_query_bounds_require_timestamps(field: str, bound: str) -> None:
    with pytest.raises(ValidationError):
        PlanQuery.model_validate({field: {bound: "2026-09-22"}})


def test_created_filter_and_sort_use_time_of_day(store: DocumentStore) -> None:
    for name, stamp in [
        ("alpha", "2026-09-22T12:00:00.123456Z"),
        ("beta", "2026-09-22T13:00:00.123456+02:00"),
        ("gamma", "2026-09-22T12:00:00.123457Z"),
    ]:
        store.write(
            Layout().plan(name),
            Document(metadata=PlanMetadata.model_validate({"created": stamp}), body=""),
        )
    assert names(store, PlanQuery(sort="created")) == ["beta", "alpha", "gamma"]
    query = PlanQuery.model_validate(
        {
            "created_range": {
                "gte": "2026-09-22T14:00:00.123456+02:00",
                "lte": "2026-09-22T12:00:00.123456Z",
            }
        }
    )
    assert names(store, query) == ["alpha"]
