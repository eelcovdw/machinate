import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from machinate.models.documents import ParsedDocument, PlanMetadata, TaskMetadata
from machinate.models.operations import DocumentQuery, PlanQuery, TaskQuery
from machinate.services.document import _sort_records
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
        path = Layout().plan_path(name)
        store.create(
            path,
            ParsedDocument(
                metadata=PlanMetadata.model_validate(
                    {
                        "created_at": datetime(2026, 9, day, tzinfo=UTC),
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
    records = store.list(Layout().plan_collection(), PlanMetadata, query)
    if query.sort == "last_activity_at":
        ordered = sorted(records, key=lambda record: record.name)
        ordered.sort(
            key=lambda record: store.read_last_activity_at(
                record.path,
                Layout().task_collection(record.name),
                Layout().context_collection(record.name),
            ),
            reverse=query.descending,
        )
        if query.limit is not None:
            ordered = ordered[: query.limit]
        return [record.name for record in ordered]
    return [record.name for record in _sort_records(records, query)]


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
        (PlanQuery(sort="last_activity_at", descending=True), ["beta", "gamma", "alpha"]),
        (PlanQuery(sort="created_at"), ["alpha", "beta", "gamma"]),
        (PlanQuery(sort="modified_at"), ["alpha", "beta", "gamma"]),
        (
            PlanQuery(
                statuses={"draft", "done"}, sort="last_activity_at", descending=True, limit=1
            ),
            ["beta"],
        ),
    ],
)
def test_query_mechanics(store: DocumentStore, query: PlanQuery, expected: list[str]) -> None:
    assert names(store, query) == expected


def test_modified_at_is_the_file_mtime(store: DocumentStore, tmp_path: Path) -> None:
    record = next(record for record in store.list(Layout().plan_collection(), PlanMetadata))
    expected = datetime.fromtimestamp((tmp_path / record.path).stat().st_mtime, UTC)
    assert record.modified_at == expected


def test_created_sort_uses_time_of_day(store: DocumentStore) -> None:
    """Microsecond and offset differences order by instant, not the literal value."""
    for name, stamp in [
        ("alpha", "2026-09-22T12:00:00.123456Z"),
        ("beta", "2026-09-22T13:00:00.123456+02:00"),
        ("gamma", "2026-09-22T12:00:00.123457Z"),
    ]:
        store.write(
            Layout().plan_path(name),
            ParsedDocument(metadata=PlanMetadata.model_validate({"created_at": stamp}), body=""),
        )
    assert names(store, PlanQuery(sort="created_at")) == ["beta", "alpha", "gamma"]


@pytest.mark.parametrize("folder", ["tasks", "context"])
def test_activity_precedes_filters_and_limit(
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
    query = PlanQuery(sort="last_activity_at", descending=True, limit=1)
    collection = Layout().plan_collection()
    records = store.list(collection, PlanMetadata, query)
    assert {record.name for record in records} == {"alpha", "beta", "gamma"}
    alpha = next(record for record in records if record.name == "alpha")
    assert store.read_last_activity_at(
        alpha.path,
        Layout().task_collection("alpha"),
        Layout().context_collection("alpha"),
    ) == datetime.fromtimestamp(300, UTC)
    assert names(store, query) == ["alpha"]


def test_discovery_empty_scopes_and_malformed_documents(
    store: DocumentStore, tmp_path: Path
) -> None:
    assert DocumentStore(tmp_path / "absent").list(Layout().plan_collection(), PlanMetadata) == []
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
    frontmatter = "---\ncreated_at: 2026-09-22T00:00:00Z\n---\nbody\n"
    (tasks / "visible.md").write_text(frontmatter)
    (tasks / ".hidden.md").write_text(frontmatter)
    (tasks / ".#lock.md").symlink_to(tasks / "missing.md")
    (tasks / "real.md").write_text(frontmatter)
    (tasks / "link.md").symlink_to(tasks / "real.md")
    external = tmp_path / "external"
    external.mkdir()
    (external / "nested.md").write_text(frontmatter)
    (tasks / "linked").symlink_to(external, target_is_directory=True)
    records = store.list(Layout().task_collection("alpha"), TaskMetadata)
    assert {record.name for record in records} == {"visible", "real", "link"}


def test_non_directory_collection_is_error(store: DocumentStore) -> None:
    with pytest.raises(StorageError):
        store.list(
            DocumentCollection(
                path=PurePosixPath("plans/alpha/plan.md"), pattern=PurePosixPath("*.md")
            ),
            PlanMetadata,
        )


def test_nested_document_names_support_ordering(store: DocumentStore, tmp_path: Path) -> None:
    collection = DocumentCollection(
        path=PurePosixPath("alpha", "tasks"), pattern=PurePosixPath("**/*.md")
    )
    for name in ("two/login", "one/login", "login.v2"):
        path = collection.path / f"{name}.md"
        store.create(
            path,
            ParsedDocument(
                metadata=TaskMetadata(created_at=datetime(2026, 9, 22, tzinfo=UTC)), body=""
            ),
        )
        os.utime(tmp_path / path, (100, 100))

    for query in (
        DocumentQuery(),
        DocumentQuery(sort="created_at", descending=True),
    ):
        records = _sort_records(store.list(collection, TaskMetadata, query), query)
        assert [record.name for record in records] == ["login.v2", "one/login", "two/login"]

    query = DocumentQuery(descending=True, limit=1)
    records = _sort_records(store.list(collection, TaskMetadata, query), query)
    assert [record.name for record in records] == ["two/login"]


def test_task_status_filter(store: DocumentStore) -> None:
    for name, status in [("alpha", "todo"), ("beta", "in-progress"), ("nested/gamma", "done")]:
        path = Layout().task_path("alpha", name)
        store.create(
            path,
            ParsedDocument(
                metadata=TaskMetadata.model_validate(
                    {"created_at": datetime(2026, 9, 22, tzinfo=UTC), "status": status}
                ),
                body="",
            ),
        )
    query = TaskQuery(statuses={"done"})
    records = _sort_records(
        store.list(Layout().task_collection("alpha"), TaskMetadata, query), query
    )
    assert [record.name for record in records] == ["nested/gamma"]
