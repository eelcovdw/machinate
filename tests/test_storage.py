import json
import logging
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError
from upath import UPath

from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentExistsError,
    DocumentStore,
    InvalidDocumentError,
    Layout,
    Metadata,
    MissingDocumentError,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
    StorageError,
    SymbolicLinkError,
    TaskMetadata,
)
from machinate.storage.summary import derive_summary


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    return DocumentStore(UPath(tmp_path))


@pytest.fixture
def document() -> Document[TaskMetadata]:
    return Document(
        metadata=TaskMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body="# Task\n"
    )


@pytest.mark.parametrize("body", ["", "\n\n# Café\n\n", "\r\n# Task\r\n\r\n", "no final newline"])
def test_document_round_trip(store: DocumentStore, body: str) -> None:
    metadata = TaskMetadata.model_validate(
        {"created": "2026-09-22T00:00:00Z", "status": "in-progress", "custom": {"tags": ["one", 2]}}
    )
    document = Document(metadata=metadata, body=body)
    document.metadata.summary = derive_summary(body)
    store.create("auth/tasks/login.md", document)
    assert store.read("auth/tasks/login.md", TaskMetadata) == document
    document.metadata.status = "done"
    store.write("auth/tasks/login.md", document)
    assert store.read("auth/tasks/login.md", TaskMetadata) == document


def test_tag_validation_and_deduplication() -> None:
    metadata = PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC), tags=[" A ", "a", "b", "A"])
    assert metadata.tags == ["A", "b"]
    assert "tags" in PlanMetadata.model_json_schema()["properties"]
    for invalid in ("", "   ", "bad\x01"):
        with pytest.raises(ValidationError):
            PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC), tags=[invalid])


def test_tags_round_trip(store: DocumentStore) -> None:
    document = Document(
        metadata=TaskMetadata(created=datetime(2026, 9, 22, tzinfo=UTC), tags=["frontend", "v2"]),
        body="body",
    )
    store.create("auth/tasks/login.md", document)
    assert store.read("auth/tasks/login.md", TaskMetadata).metadata.tags == ["frontend", "v2"]
    document.metadata.tags = ["backend"]
    store.write("auth/tasks/login.md", document)
    assert store.read("auth/tasks/login.md", TaskMetadata).metadata.tags == ["backend"]


def test_existing_frontmatter_preserved(store: DocumentStore, tmp_path: Path) -> None:
    body = "\r\n\r\n# Résumé  \r\n---\r\nlast line"
    (tmp_path / "note.md").write_bytes(
        (
            "---\r\ncreated: 2026-09-22T00:00:00Z\r\ncustom:\r\n  nested: [true, 7]\r\n---\r\n"
            + body
        ).encode()
    )
    document = store.read("note.md", ContextMetadata)
    document.metadata.summary = "updated"
    store.write("note.md", document)
    result = store.read("note.md", ContextMetadata)
    assert result.body == body
    assert result.metadata.model_extra == {"custom": {"nested": [True, 7]}}
    assert json.loads(result.model_dump_json())["metadata"]["created"] == "2026-09-22T00:00:00Z"


@pytest.mark.parametrize("model", [Metadata, PlanMetadata, TaskMetadata, ContextMetadata])
def test_creation_timestamp_required(model: type[Metadata]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({})
    with pytest.raises(ValidationError):
        model.model_validate({"created": "not a date"})


@pytest.mark.parametrize(
    ("model", "statuses"),
    [(PlanMetadata, ["draft", "active", "done"]), (TaskMetadata, ["todo", "in-progress", "done"])],
)
def test_status_validation(model: type[Metadata], statuses: list[str]) -> None:
    for status in statuses:
        metadata = model.model_validate({"created": "2026-09-22T00:00:00Z", "status": status})
        with pytest.raises(ValidationError):
            metadata.status = "invalid"  # pyright: ignore[reportAttributeAccessIssue]
        assert metadata.model_dump()["status"] == status
    with pytest.raises(ValidationError):
        model.model_validate({"created": "2026-09-22T00:00:00Z", "status": "invalid"})


def test_metadata_assignment() -> None:
    metadata = Metadata(created=datetime(2026, 9, 22, tzinfo=UTC))
    with pytest.raises(ValidationError):
        metadata.created = "invalid"  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(ValidationError):
        metadata.summary = []  # pyright: ignore[reportAttributeAccessIssue]
    context = ContextMetadata.model_validate(
        {"created": "2026-09-22T00:00:00Z", "status": "custom"}
    )
    assert context.model_extra == {"status": "custom"}


def test_duplicate_and_missing(store: DocumentStore, document: Document[TaskMetadata]) -> None:
    store.create("note.md", document)
    with pytest.raises(DocumentExistsError) as error:
        store.create("note.md", Document(metadata=document.metadata, body="replacement"))
    assert error.value.path == PurePosixPath("note.md")
    assert isinstance(error.value.reason, FileExistsError)
    assert store.read("note.md", TaskMetadata) == document
    with pytest.raises(MissingDocumentError):
        store.write("missing.md", document)
    with pytest.raises(MissingDocumentError):
        store.read("missing.md", TaskMetadata)


@pytest.mark.parametrize(
    "content",
    [
        "---\ncreated: 2026-09-22T00:00:00Z",
        "---\nsummary: missing date\n---\n",
        "---\n[\n---\n",
        "---\n- list\n---\n",
        "---\ncreated: 2026-09-22T00:00:00Z\nstatus: invalid\n---\n",
    ],
)
def test_invalid_documents(store: DocumentStore, tmp_path: Path, content: str) -> None:
    (tmp_path / "bad.md").write_text(content)
    with pytest.raises(InvalidDocumentError) as error:
        store.read("bad.md", TaskMetadata)
    assert error.value.path == PurePosixPath("bad.md")
    assert error.value.__cause__ is error.value.reason


def test_missing_frontmatter_uses_defaults(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "bare.md").write_text("just a body\n")
    document = store.read("bare.md", TaskMetadata)
    assert document.body == "just a body\n"
    assert document.metadata.status == "todo"
    assert document.metadata.tags == []
    assert document.metadata.summary is None


def test_missing_frontmatter_logs_debug(
    store: DocumentStore, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "bare.md").write_text("body")
    with caplog.at_level(logging.DEBUG, logger="machinate.storage.document_store"):
        store.read("bare.md", TaskMetadata)
    assert "Missing YAML frontmatter in bare.md; using defaults" in caplog.text


def test_missing_frontmatter_created_from_mtime(store: DocumentStore, tmp_path: Path) -> None:
    target = tmp_path / "bare.md"
    target.write_text("body")
    expected = datetime.fromtimestamp(target.stat().st_mtime, UTC)
    document = store.read("bare.md", PlanMetadata)
    assert document.metadata.created == expected
    assert document.metadata.status == "draft"


def test_empty_file_is_treated_as_body(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("")
    document = store.read("empty.md", ContextMetadata)
    assert document.body == ""
    assert document.metadata.tags == []


@pytest.mark.parametrize(
    "name", ["", " ", ".", "..", "../escape", "a/b", "a\\b", "C:drive", "bad\n"]
)
def test_layout_rejects_names(name: str) -> None:
    layout = Layout()
    with pytest.raises(ValidationError):
        layout.plan(name)
    for operation in (layout.task, layout.context):
        if name == "a/b":
            folder = "tasks" if operation == layout.task else "context"
            assert operation("valid", name) == PurePosixPath("plans", "valid", folder, "a/b.md")
        else:
            with pytest.raises(ValidationError):
                operation("valid", name)
        with pytest.raises(ValidationError):
            operation(name, "valid")


def test_layout() -> None:
    layout = Layout()
    assert layout.project() == PurePosixPath("project.md")
    assert layout.plan("auth") == PurePosixPath("plans/auth/plan.md")
    assert layout.task("auth", "login") == PurePosixPath("plans/auth/tasks/login.md")
    assert layout.context("auth", "research") == PurePosixPath("plans/auth/context/research.md")


@pytest.mark.parametrize(
    "path", ["", "/absolute", "../escape", "a/../escape", "C:/escape", "a\\b", "bad\x00"]
)
def test_storage_path_boundaries(
    store: DocumentStore, document: Document[TaskMetadata], path: str
) -> None:
    with pytest.raises(ValidationError):
        store.create(path, document)
    with pytest.raises(ValidationError):
        store.write(path, document)
    with pytest.raises(ValidationError):
        store.read(path, TaskMetadata)
    with pytest.raises(ValidationError):
        store.metadata(path)
    with pytest.raises(ValidationError):
        store.discover(path)


def test_discovery_and_timestamps(
    store: DocumentStore, document: Document[TaskMetadata], tmp_path: Path
) -> None:
    store.create("auth/tasks/login.md", document)
    store.create("project.md", document)
    records = store.discover()
    assert [(record.path.as_posix(), record.kind) for record in records] == [
        ("auth", "directory"),
        ("project.md", "file"),
    ]
    record = store.discover("auth/tasks")[0]
    assert record == store.metadata("auth/tasks/login.md")
    assert record.modified == datetime.fromtimestamp((tmp_path / record.path).stat().st_mtime, UTC)
    assert json.loads(record.model_dump_json())["path"] == "auth/tasks/login.md"
    (tmp_path / "empty").mkdir()
    assert store.discover("empty") == []
    with pytest.raises(MissingDocumentError):
        store.discover("missing")
    with pytest.raises(StorageError):
        store.discover("project.md")


def test_failed_atomic_update_keeps_original(
    store: DocumentStore,
    document: Document[TaskMetadata],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.create("note.md", document)

    def fail_replace(_self: Path, _target: str) -> None:
        raise PermissionError("replacement denied")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(StorageError) as error:
        store.write("note.md", Document(metadata=document.metadata, body="new"))
    assert isinstance(error.value.reason, PermissionError)
    assert store.read("note.md", TaskMetadata) == document
    assert list(tmp_path.iterdir()) == [tmp_path / "note.md"]


def test_state_round_trip(tmp_path: Path) -> None:
    store = ProjectStateStore(UPath(tmp_path / "nested" / "machinate.toml"))
    with pytest.raises(MissingDocumentError):
        store.read()
    state = ProjectState(project_name="Café", current_plan="auth")
    store.write(state)
    assert store.read() == state
    state.current_plan = None
    store.write(state)
    assert store.read() == state
    assert "current_plan" not in store.path.read_text()
    with pytest.raises(ValidationError):
        state.current_plan = "../escape"


@pytest.mark.parametrize(
    "text", ["", "invalid [", 'project_name = "../bad"', 'current_plan = "auth"']
)
def test_invalid_state(tmp_path: Path, text: str) -> None:
    path = UPath(tmp_path / "machinate.toml")
    path.write_text(text)
    with pytest.raises(InvalidDocumentError):
        ProjectStateStore(path).read()


def test_failed_state_write_keeps_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = UPath(tmp_path / "nested" / "machinate.toml")
    store = ProjectStateStore(path)
    original = ProjectState(project_name="Café", current_plan="auth")
    store.write(original)

    def fail_replace(_self: Path, _target: str) -> None:
        raise PermissionError("replacement denied")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(StorageError) as error:
        store.write(ProjectState(project_name="Café"))
    assert isinstance(error.value.reason, PermissionError)
    assert store.read() == original
    nested = tmp_path / "nested"
    assert list(nested.iterdir()) == [nested / "machinate.toml"]


def test_successful_update_replaces_file(
    store: DocumentStore, document: Document[TaskMetadata], tmp_path: Path
) -> None:
    store.create("note.md", document)
    target = tmp_path / "note.md"
    target.chmod(0o640)
    original = target.read_bytes()
    with target.open("rb") as old_file:
        store.write("note.md", Document(metadata=document.metadata, body="new content"))
        assert old_file.read() == original
    assert store.read("note.md", TaskMetadata).body == "new content"
    assert target.stat().st_mode & 0o777 == 0o640
    assert list(tmp_path.iterdir()) == [target]


def test_null_extra_metadata_preserved(store: DocumentStore, tmp_path: Path) -> None:
    document = Document(
        metadata=Metadata.model_validate(
            {"created": "2026-09-22T00:00:00Z", "custom": {"owner": None}}
        ),
        body="# Note\n",
    )
    store.create("note.md", document)
    assert "owner: null" in (tmp_path / "note.md").read_text()
    assert store.read("note.md", Metadata) == document


def test_unset_summary_omitted(store: DocumentStore, tmp_path: Path) -> None:
    document = Document(
        metadata=Metadata.model_validate({"created": "2026-09-22T00:00:00Z"}), body="# Note\n"
    )
    store.create("note.md", document)
    assert "summary" not in (tmp_path / "note.md").read_text()


def test_write_rejects_symlink(
    store: DocumentStore,
    document: Document[TaskMetadata],
    tmp_path: Path,
) -> None:
    external = tmp_path / "outside.md"
    external.write_bytes(b"original\n")
    (tmp_path / "note.md").symlink_to(external)

    with pytest.raises(SymbolicLinkError):
        store.write("note.md", Document(metadata=document.metadata, body="new"))

    assert (tmp_path / "note.md").is_symlink()
    assert external.read_bytes() == b"original\n"


def test_create_rejects_symlink(
    store: DocumentStore, document: Document[TaskMetadata], tmp_path: Path
) -> None:
    external = tmp_path / "outside.md"
    external.write_bytes(b"original\n")
    (tmp_path / "note.md").symlink_to(external)

    with pytest.raises(DocumentExistsError):
        store.create("note.md", document)

    assert (tmp_path / "note.md").is_symlink()
    assert external.read_bytes() == b"original\n"


def test_invalid_utf8(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "bad.md").write_bytes(b"\xff")
    with pytest.raises(InvalidDocumentError) as error:
        store.read("bad.md", Metadata)
    assert isinstance(error.value.reason, UnicodeDecodeError)


def test_io_errors_have_path_and_reason(
    store: DocumentStore, document: Document[TaskMetadata], tmp_path: Path
) -> None:
    (tmp_path / "directory").mkdir()
    with pytest.raises(StorageError):
        store.read("directory", Metadata)
    with pytest.raises(StorageError):
        store.write("directory", document)
    (tmp_path / "file").write_text("blocking parent")
    with pytest.raises(StorageError) as error:
        store.create("file/child.md", document)
    assert error.value.path == PurePosixPath("file/child.md")
    assert isinstance(error.value.reason, OSError)
    state_store = ProjectStateStore(UPath(tmp_path / "file" / "state.toml"))
    with pytest.raises(StorageError):
        state_store.write(ProjectState(project_name="demo"))


def test_yaml_uses_block_style(store: DocumentStore, tmp_path: Path) -> None:
    document = Document(
        metadata=Metadata.model_validate(
            {"created": "2026-09-22T00:00:00Z", "custom": {"owner": "Alice"}}
        ),
        body="# Note\n",
    )
    store.create("note.md", document)
    text = (tmp_path / "note.md").read_text()
    assert "\ncreated: 2026-09-22 00:00:00+00:00\n" in text
    assert "\ncustom:\n  owner: Alice\n" in text
    assert store.read("note.md", Metadata) == document


def test_cleanup_failure_preserves_write_error(
    store: DocumentStore,
    document: Document[TaskMetadata],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.create("note.md", document)
    original_error = PermissionError("replacement denied")

    def fail_replace(_self: Path, _target: str) -> None:
        raise original_error

    def fail_unlink(_self: Path, **_kwargs: object) -> None:
        raise PermissionError("cleanup denied")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_replace)
        patch.setattr(Path, "unlink", fail_unlink)
        with pytest.raises(StorageError) as error:
            store.write("note.md", Document(metadata=document.metadata, body="new"))

    assert error.value.path == PurePosixPath("note.md")
    assert error.value.reason is original_error
    assert error.value.__cause__ is original_error
    leftover = next(path for path in tmp_path.iterdir() if path.name != "note.md")
    assert str(leftover) in error.value.__notes__[0]
    assert "cleanup denied" in error.value.__notes__[0]
    assert store.read("note.md", TaskMetadata) == document
    leftover.unlink()


@pytest.mark.parametrize("value", ["2026-09-22", "2026-09-22T12:30:00"])
@pytest.mark.parametrize("model", [Metadata, PlanMetadata, TaskMetadata, ContextMetadata])
def test_created_requires_timezone(model: type[Metadata], value: str) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({"created": value})


def test_created_preserves_precision_and_offset(store: DocumentStore) -> None:
    metadata = TaskMetadata.model_validate({"created": "2026-09-22T12:34:56.123456+02:00"})
    store.create("precise.md", Document(metadata=metadata, body=""))
    result = store.read("precise.md", TaskMetadata)
    assert result.metadata.created.isoformat() == "2026-09-22T12:34:56.123456+02:00"
