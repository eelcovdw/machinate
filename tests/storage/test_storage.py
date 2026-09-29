import json
import logging
import unicodedata
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
from pydantic import TypeAdapter, ValidationError

from machinate.models.documents import (
    NAME_ADAPTER,
    NESTED_NAME_ADAPTER,
    ContextMetadata,
    Metadata,
    ParsedDocument,
    PlanMetadata,
    TaskMetadata,
    derive_summary,
)
from machinate.storage import (
    DocumentExistsError,
    DocumentStore,
    InvalidDocumentError,
    Layout,
    MissingDocumentError,
    ProjectState,
    ProjectStateStore,
    StorageError,
    SymbolicLinkError,
)


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    return DocumentStore(tmp_path)


@pytest.fixture
def document() -> ParsedDocument[TaskMetadata]:
    return ParsedDocument(
        metadata=TaskMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body="# Task\n"
    )


@pytest.mark.parametrize("body", ["", "\n\n# Café\n\n", "\r\n# Task\r\n\r\n", "no final newline"])
def test_document_round_trip(store: DocumentStore, body: str) -> None:
    metadata = TaskMetadata.model_validate(
        {"created": "2026-09-22T00:00:00Z", "status": "in-progress", "custom": {"tags": ["one", 2]}}
    )
    document = ParsedDocument(metadata=metadata, body=body)
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
    document = ParsedDocument(
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


def test_duplicate_and_missing(
    store: DocumentStore, document: ParsedDocument[TaskMetadata]
) -> None:
    store.create("note.md", document)
    with pytest.raises(DocumentExistsError) as error:
        store.create("note.md", ParsedDocument(metadata=document.metadata, body="replacement"))
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


def test_glob_files_matches_regular_files_only(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.md").write_text("one")
    (tmp_path / "a" / "two.txt").write_text("two")
    (tmp_path / "a" / "sub").mkdir()
    (tmp_path / "a" / "sub" / "three.md").write_text("three")
    assert sorted(store.glob_files(PurePosixPath("a"), ["**/*.md"])) == [
        PurePosixPath("a/one.md"),
        PurePosixPath("a/sub/three.md"),
    ]
    assert store.glob_files(PurePosixPath("missing"), ["**/*.md"]) == []


def test_glob_files_includes_dot_prefixed_files(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / ".hidden.md").write_text("hidden")
    (tmp_path / "a" / "visible.md").write_text("visible")
    assert sorted(store.glob_files(PurePosixPath("a"), ["**/*.md"])) == [
        PurePosixPath("a/.hidden.md"),
        PurePosixPath("a/visible.md"),
    ]


def test_read_text_returns_raw_frontmatter(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "raw.md").write_text("---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n")
    assert store.read_text("raw.md") == "---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n"


def test_read_text_errors_are_typed(store: DocumentStore, tmp_path: Path) -> None:
    with pytest.raises(MissingDocumentError):
        store.read_text("missing.md")
    (tmp_path / "binary.md").write_bytes(b"\xff\xfe")
    with pytest.raises(InvalidDocumentError) as error:
        store.read_text("binary.md")
    assert error.value.path == PurePosixPath("binary.md")


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
    records = [r for r in caplog.records if r.name == "machinate.storage.document_store"]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].args == (PurePosixPath("bare.md"),)


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


def test_utf8_bom_is_stripped_on_read(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "bom.md").write_bytes(
        b"\xef\xbb\xbf---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n"
    )
    document = store.read("bom.md", TaskMetadata)
    assert document.body == "body\n"
    assert store.read_text("bom.md") == "---\ncreated: 2026-09-22T00:00:00Z\n---\nbody\n"


def test_empty_frontmatter_block_uses_defaults(store: DocumentStore, tmp_path: Path) -> None:
    target = tmp_path / "empty-block.md"
    target.write_text("---\n---\nbody\n")
    expected = datetime.fromtimestamp(target.stat().st_mtime, UTC)
    document = store.read("empty-block.md", TaskMetadata)
    assert document.body == "body\n"
    assert document.metadata.status == "todo"
    assert document.metadata.created == expected


def test_scalar_and_non_string_frontmatter_values_are_coerced(
    store: DocumentStore, tmp_path: Path
) -> None:
    (tmp_path / "edited.md").write_text(
        "---\ncreated: 2026-09-22T00:00:00Z\nsummary: 1.5\ntags: v2\n---\nbody\n"
    )
    document = store.read("edited.md", TaskMetadata)
    assert document.metadata.summary == "1.5"
    assert document.metadata.tags == ["v2"]

    (tmp_path / "tags.md").write_text(
        "---\ncreated: 2026-09-22T00:00:00Z\ntags: [v2, 2026]\n---\nbody\n"
    )
    assert store.read("tags.md", TaskMetadata).metadata.tags == ["v2", "2026"]


def test_glob_files_skips_dangling_symlinks(store: DocumentStore, tmp_path: Path) -> None:
    directory = tmp_path / "a"
    directory.mkdir()
    (directory / "one.md").write_text("one")
    (directory / ".#one.md").symlink_to(directory / "missing.md")
    assert store.glob_files(PurePosixPath("a"), ["**/*.md"]) == [PurePosixPath("a/one.md")]


def test_glob_files_drops_parent_escape(store: DocumentStore, tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "outside.md").write_text("outside")
    assert store.glob_files(PurePosixPath("a"), ["../*.md"]) == []


@pytest.mark.parametrize(
    "name", ["", " ", ".", "..", "../escape", "a/b", "a\\b", "C:drive", "bad\n"]
)
def test_names_reject_invalid_values(name: str) -> None:
    with pytest.raises(ValidationError):
        NAME_ADAPTER.validate_python(name)
    if name == "a/b":
        assert NESTED_NAME_ADAPTER.validate_python(name) == "a/b"
    else:
        with pytest.raises(ValidationError):
            NESTED_NAME_ADAPTER.validate_python(name)


def test_layout() -> None:
    layout = Layout()
    assert layout.plan("auth") == PurePosixPath("plans/auth/plan.md")
    assert layout.task("auth", "login") == PurePosixPath("plans/auth/tasks/login.md")
    assert layout.context("auth", "research") == PurePosixPath("plans/auth/context/research.md")


@pytest.mark.parametrize(
    "path", ["", "/absolute", "../escape", "a/../escape", "C:/escape", "a\\b", "bad\x00"]
)
def test_storage_path_boundaries(
    store: DocumentStore, document: ParsedDocument[TaskMetadata], path: str
) -> None:
    with pytest.raises(ValidationError):
        store.create(path, document)
    with pytest.raises(ValidationError):
        store.write(path, document)
    with pytest.raises(ValidationError):
        store.read(path, TaskMetadata)
    with pytest.raises(ValidationError):
        store.metadata(path)


def test_case_only_duplicate_create_is_rejected(
    store: DocumentStore, document: ParsedDocument[TaskMetadata]
) -> None:
    store.create("Login.md", document)
    with pytest.raises(DocumentExistsError) as error:
        store.create("login.md", document)
    assert error.value.path == PurePosixPath("login.md")
    assert store.read("Login.md", TaskMetadata) == document


def test_state_round_trip(tmp_path: Path) -> None:
    store = ProjectStateStore(tmp_path / "nested" / "machinate.toml")
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


def test_state_write_rejects_symlink(tmp_path: Path) -> None:
    external = tmp_path / "shared.toml"
    external.write_text('project_name = "demo"\n')
    link = tmp_path / "machinate.toml"
    link.symlink_to(external)

    with pytest.raises(SymbolicLinkError) as error:
        ProjectStateStore(link).write(ProjectState(project_name="demo", current_plan="auth"))
    assert error.value.reason is None
    assert error.value.path == link

    assert link.is_symlink()
    assert external.read_text() == 'project_name = "demo"\n'


@pytest.mark.parametrize(
    "text",
    [
        "",
        "invalid [",
        'project_name = "../bad"',
        'current_plan = "auth"',
        'project_name = "demo"\nextra = "x"',
    ],
)
def test_invalid_state(tmp_path: Path, text: str) -> None:
    path = tmp_path / "machinate.toml"
    path.write_text(text)
    with pytest.raises(InvalidDocumentError):
        ProjectStateStore(path).read()


def test_successful_update_replaces_file(
    store: DocumentStore, document: ParsedDocument[TaskMetadata], tmp_path: Path
) -> None:
    store.create("note.md", document)
    target = tmp_path / "note.md"
    target.chmod(0o640)
    original = target.read_bytes()
    with target.open("rb") as old_file:
        store.write("note.md", ParsedDocument(metadata=document.metadata, body="new content"))
        assert old_file.read() == original
    assert store.read("note.md", TaskMetadata).body == "new content"
    assert target.stat().st_mode & 0o777 == 0o640
    assert list(tmp_path.iterdir()) == [target]


def test_null_extra_metadata_preserved(store: DocumentStore, tmp_path: Path) -> None:
    document = ParsedDocument(
        metadata=Metadata.model_validate(
            {"created": "2026-09-22T00:00:00Z", "custom": {"owner": None}}
        ),
        body="# Note\n",
    )
    store.create("note.md", document)
    assert "owner: null" in (tmp_path / "note.md").read_text()
    assert store.read("note.md", Metadata) == document


def test_unset_summary_omitted(store: DocumentStore, tmp_path: Path) -> None:
    document = ParsedDocument(
        metadata=Metadata.model_validate({"created": "2026-09-22T00:00:00Z"}), body="# Note\n"
    )
    store.create("note.md", document)
    assert "summary" not in (tmp_path / "note.md").read_text()


def test_write_rejects_symlink(
    store: DocumentStore,
    document: ParsedDocument[TaskMetadata],
    tmp_path: Path,
) -> None:
    external = tmp_path / "outside.md"
    external.write_bytes(b"original\n")
    (tmp_path / "note.md").symlink_to(external)

    with pytest.raises(SymbolicLinkError) as error:
        store.write("note.md", ParsedDocument(metadata=document.metadata, body="new"))
    assert error.value.reason is None
    assert error.value.path == PurePosixPath("note.md")

    assert (tmp_path / "note.md").is_symlink()
    assert external.read_bytes() == b"original\n"


def test_create_rejects_symlink(
    store: DocumentStore, document: ParsedDocument[TaskMetadata], tmp_path: Path
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
    store: DocumentStore, document: ParsedDocument[TaskMetadata], tmp_path: Path
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
    state_store = ProjectStateStore(tmp_path / "file" / "state.toml")
    with pytest.raises(StorageError):
        state_store.write(ProjectState(project_name="demo"))


def test_yaml_uses_block_style(store: DocumentStore, tmp_path: Path) -> None:
    document = ParsedDocument(
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


def test_created_preserves_precision_and_offset(store: DocumentStore) -> None:
    metadata = TaskMetadata.model_validate({"created": "2026-09-22T12:34:56.123456+02:00"})
    store.create("precise.md", ParsedDocument(metadata=metadata, body=""))
    result = store.read("precise.md", TaskMetadata)
    assert result.metadata.created.isoformat() == "2026-09-22T12:34:56.123456+02:00"


def test_names_are_normalized_to_nfc() -> None:
    decomposed = "Cafe\u0301"
    composed = unicodedata.normalize("NFC", decomposed)
    assert composed != decomposed
    assert NAME_ADAPTER.validate_python(decomposed) == composed
    assert NESTED_NAME_ADAPTER.validate_python(f"topic/{decomposed}.md") == f"topic/{composed}"


@pytest.mark.parametrize(
    ("adapter", "name", "expected"),
    [
        (NAME_ADAPTER, "spec.md", "spec"),
        (NAME_ADAPTER, "Spec.MD", "Spec"),
        (NESTED_NAME_ADAPTER, "topic/spec.md", "topic/spec"),
    ],
)
def test_names_ignore_markdown_suffix(adapter: TypeAdapter[str], name: str, expected: str) -> None:
    assert adapter.validate_python(name) == expected
