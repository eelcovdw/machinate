import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

from machinate.models.documents import ParsedDocument, PlanMetadata, TaskMetadata
from machinate.models.operations import DocumentQuery, PlanQuery, TaskQuery
from machinate.storage import (
    DocumentCollection,
    DocumentStore,
    InvalidDocumentError,
    Layout,
    StorageError,
)


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    store = DocumentStore(tmp_path)
    for name, day, status, body, stamp, tags in [
        ("alpha", 1, "active", "OAuth", 100, ["frontend"]),
        ("beta", 2, "draft", "Other\n\nOAuth body", 200, ["backend", "v2"]),
        ("gamma", 2, "done", "OAuth", 200, ["frontend", "v2"]),
    ]:
        path = Layout().plan(name)
        store.create(
            path,
            ParsedDocument(
                metadata=PlanMetadata.model_validate(
                    {
                        "created": datetime(2026, 9, day, tzinfo=UTC),
                        "status": status,
                        "tags": tags,
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
        (PlanQuery(statuses=set()), []),
        (PlanQuery(statuses={"active", "done"}), ["alpha", "gamma"]),
        (PlanQuery(tags={"frontend"}), ["alpha", "gamma"]),
        (PlanQuery(tags={"frontend", "backend"}), ["alpha", "beta", "gamma"]),
        (PlanQuery(tags={"v2"}, statuses={"done"}), ["gamma"]),
        (PlanQuery(sort="name", descending=True, limit=2), ["gamma", "beta"]),
        (PlanQuery(sort="updated", descending=True), ["beta", "gamma", "alpha"]),
        (PlanQuery(sort="created"), ["alpha", "beta", "gamma"]),
        (PlanQuery(statuses={"draft", "done"}, sort="updated", descending=True, limit=1), ["beta"]),
    ],
)
def test_query_mechanics(store: DocumentStore, query: PlanQuery, expected: list[str]) -> None:
    assert names(store, query) == expected


def test_created_sort_uses_time_of_day(store: DocumentStore) -> None:
    """Microsecond and offset differences order by instant, not the literal value."""
    for name, stamp in [
        ("alpha", "2026-09-22T12:00:00.123456Z"),
        ("beta", "2026-09-22T13:00:00.123456+02:00"),
        ("gamma", "2026-09-22T12:00:00.123457Z"),
    ]:
        store.write(
            Layout().plan(name),
            ParsedDocument(metadata=PlanMetadata.model_validate({"created": stamp}), body=""),
        )
    assert names(store, PlanQuery(sort="created")) == ["beta", "alpha", "gamma"]


@pytest.mark.parametrize(
    "data",
    [
        {"limit": 0},
        {"limit": -1},
        {"statuses": ["invalid"]},
        {"tags": [""]},
        {"tags": ["  "]},
        {"tags": ["bad\x01"]},
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
    child = tmp_path / "plans" / "alpha" / folder / "nested" / "bad.md"
    child.parent.mkdir(parents=True)
    child.write_text("deliberately invalid document")
    os.utime(child, (300, 300))
    unrelated = child.with_suffix(".txt")
    unrelated.write_text("unrelated")
    os.utime(unrelated, (900, 900))
    outside = tmp_path / "plans" / "alpha" / "unrelated.md"
    outside.write_text("also outside activity scopes")
    os.utime(outside, (900, 900))
    query = PlanQuery(sort="updated", descending=True, limit=1)
    records = store.list(Layout().plan_collection(), PlanMetadata, query)
    assert [record.name for record in records] == ["alpha"]
    assert records[0].last_activity_at == datetime.fromtimestamp(300, UTC)
    assert names(store, PlanQuery(sort="updated", descending=True, limit=1)) == ["alpha"]


def test_discovery_empty_scopes_and_malformed_documents(
    store: DocumentStore, tmp_path: Path
) -> None:
    assert store.list(Layout().task_collection("alpha"), TaskMetadata) == []
    (tmp_path / "plans" / "alpha" / "tasks").mkdir()
    assert store.list(Layout().task_collection("alpha"), TaskMetadata) == []
    (tmp_path / "plans" / "alpha" / "tasks" / "ignored.txt").write_text("invalid")
    (tmp_path / "plans" / "alpha" / "tasks" / "directory.md").mkdir()
    assert store.list(Layout().task_collection("alpha"), TaskMetadata) == []
    bad = tmp_path / "plans" / "alpha" / "tasks" / "nested" / "bad.md"
    bad.parent.mkdir()
    bad.write_text("---\nsummary: missing date\n---\n")
    with pytest.raises(InvalidDocumentError) as error:
        store.list(Layout().task_collection("alpha"), TaskMetadata)
    assert error.value.path == PurePosixPath("plans/alpha/tasks/nested/bad.md")
    (tmp_path / "plans" / "alpha" / "plan.md").write_text("---\nsummary: missing date\n---\n")
    with pytest.raises(InvalidDocumentError):
        store.list(Layout().plan_collection(), PlanMetadata)


def test_list_skips_dotfiles_and_dangling_symlinks(store: DocumentStore, tmp_path: Path) -> None:
    tasks = tmp_path / "plans" / "alpha" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "visible.md").write_text("---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n")
    (tasks / ".hidden.md").write_text("---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n")
    (tasks / ".#lock.md").symlink_to(tasks / "missing.md")
    records = store.list(Layout().task_collection("alpha"), TaskMetadata)
    assert [record.name for record in records] == ["visible"]


def test_list_includes_symlinked_file(store: DocumentStore, tmp_path: Path) -> None:
    tasks = tmp_path / "plans" / "alpha" / "tasks"
    tasks.mkdir(parents=True)
    frontmatter = "---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n"
    (tasks / "real.md").write_text(frontmatter)
    (tasks / "link.md").symlink_to(tasks / "real.md")
    records = store.list(Layout().task_collection("alpha"), TaskMetadata)
    assert {record.name for record in records} == {"real", "link"}


def test_list_does_not_follow_symlinked_directory(store: DocumentStore, tmp_path: Path) -> None:
    tasks = tmp_path / "plans" / "alpha" / "tasks"
    tasks.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (external / "nested.md").write_text("---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n")
    (tasks / "linked").symlink_to(external, target_is_directory=True)
    assert store.list(Layout().task_collection("alpha"), TaskMetadata) == []


def test_non_directory_collection_is_error(store: DocumentStore) -> None:
    with pytest.raises(StorageError):
        store.list(
            DocumentCollection(
                path=PurePosixPath("plans/alpha/plan.md"), pattern=PurePosixPath("*.md")
            ),
            PlanMetadata,
        )


def test_missing_root_is_empty(tmp_path: Path) -> None:
    assert DocumentStore(tmp_path / "absent").list(Layout().plan_collection(), PlanMetadata) == []


def test_summary_has_no_body(store: DocumentStore) -> None:
    record = store.list(Layout().plan_collection(), PlanMetadata, DocumentQuery(limit=1))[0]
    assert record.path == PurePosixPath("plans/alpha/plan.md")
    assert '"body"' not in record.model_dump_json()


@pytest.mark.parametrize("query_type", [DocumentQuery, PlanQuery, TaskQuery])
def test_unknown_query_fields_are_rejected(query_type: type[DocumentQuery]) -> None:
    with pytest.raises(ValidationError) as error:
        query_type.model_validate({"status": ["done"]})
    assert error.value.errors()[0]["type"] == "extra_forbidden"
    assert error.value.errors()[0]["loc"] == ("status",)


@pytest.mark.parametrize("folder", ["tasks", "context"])
def test_nested_document_names_support_ordering(
    store: DocumentStore, tmp_path: Path, folder: str
) -> None:
    collection = DocumentCollection(
        path=PurePosixPath("alpha", folder), pattern=PurePosixPath("**/*.md")
    )
    for name in ("two/login", "one/login", "login.v2"):
        path = collection.path / f"{name}.md"
        store.create(
            path,
            ParsedDocument(
                metadata=TaskMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body=""
            ),
        )
        os.utime(tmp_path / path, (100, 100))

    for query in (
        DocumentQuery(),
        DocumentQuery(sort="created", descending=True),
        DocumentQuery(sort="updated", descending=True),
    ):
        records = store.list(collection, TaskMetadata, query)
        assert [record.name for record in records] == ["login.v2", "one/login", "two/login"]

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
            ParsedDocument(
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
        os.utime(store.root / path, (stamp, stamp))
    records = store.list(Layout().task_collection("alpha"), TaskMetadata, query)
    assert [record.name for record in records] == expected


@pytest.mark.parametrize("status", ["draft", "active", "invalid", None])
def test_task_query_rejects_invalid_statuses(status: str | None) -> None:
    with pytest.raises(ValidationError):
        TaskQuery.model_validate({"statuses": [status]})
