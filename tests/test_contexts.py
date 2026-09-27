import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import override
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from upath import UPath

from machinate.models.context import Context, ContextSummary, ContextUpdate
from machinate.services.context import ContextService
from machinate.services.plan import PlanService
from machinate.storage import (
    ContextMetadata,
    Document,
    DocumentCollection,
    DocumentExistsError,
    DocumentQuery,
    DocumentStore,
    Layout,
    MissingDocumentError,
    PlanMetadata,
    ProjectState,
    ProjectStateStore,
)
from machinate.storage.models import ContextNameInput, NameInput


@pytest.fixture
def service(tmp_path: Path) -> ContextService:
    store = DocumentStore(UPath(tmp_path / "docs"))
    store.create(
        Layout().plan("alpha"),
        Document(metadata=PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)), body=""),
    )
    return ContextService(store, Layout())


@pytest.fixture
def metadata() -> ContextMetadata:
    return ContextMetadata.model_validate(
        {
            "created": "2026-09-22T12:34:56.123456+02:00",
            "custom": {"owner": "Alice"},
            "status": "custom status",
        }
    )


def test_create_get_duplicates_and_exact_names(
    service: ContextService, metadata: ContextMetadata
) -> None:
    context = service.create("alpha", "research", metadata, "Body\n")
    assert context == service.get("alpha", "research")
    assert context.path == PurePosixPath("plans/alpha/context/research.md")
    assert context.document == Document(metadata=metadata, body="Body\n")
    assert json.loads(context.model_dump_json())["path"] == "plans/alpha/context/research.md"
    assert Context.model_validate(json.loads(context.model_dump_json())) == context
    with pytest.raises(DocumentExistsError):
        service.create("alpha", "research", metadata, "Replacement")
    assert service.get("alpha", "research") == context


def test_create_batch_reports_partial_results(
    service: ContextService, metadata: ContextMetadata
) -> None:
    """C2: existing and invalid names become errors; later names still get created."""
    service.create("alpha", "existing", metadata)
    created, errors = service.create_batch(
        "alpha", ["new", "existing", "../bad", "later"], metadata
    )
    assert [context.name for context in created] == ["new", "later"]
    assert [(error.name, error.error) for error in errors] == [
        ("existing", "Already exists: plans/alpha/context/existing.md"),
        ("../bad", "Expected a nonempty name without path separators or control characters"),
    ]
    assert service.get("alpha", "new")
    assert service.get("alpha", "later")
    for name in ("res", "RESEARCH"):
        with pytest.raises(MissingDocumentError):
            service.get("alpha", name)
        with pytest.raises(MissingDocumentError):
            service.update("alpha", name, ContextUpdate(body="Replacement"))


def test_patches(service: ContextService, metadata: ContextMetadata) -> None:
    service.create("alpha", "research", metadata, "Body")
    context = service.update("alpha", "research", ContextUpdate(body="New body"))
    assert context.document.body == "New body"
    assert context.document.get_or_derive_summary() == "New body"
    context = service.update("alpha", "research", ContextUpdate(body=""))
    assert context.document.body == ""
    assert context.document.get_or_derive_summary() is None
    assert context.document.metadata.created.isoformat() == metadata.created.isoformat()
    assert context.document.metadata.model_extra == metadata.model_extra


def test_empty_patch(
    service: ContextService, metadata: ContextMetadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = service.create("alpha", "research", metadata, "Body")
    target = service.document_store.root / context.path
    os.utime(target.path, ns=(1234567890123456789, 1234567890123456789))
    before = target.read_bytes(), target.stat().st_mtime_ns
    context = service.get("alpha", "research")
    write = Mock(side_effect=AssertionError("empty patch must not write"))
    monkeypatch.setattr(service.document_store, "write", write)
    assert service.update("alpha", "research", ContextUpdate()) == context
    assert (target.read_bytes(), target.stat().st_mtime_ns) == before
    write.assert_not_called()


def test_missing_documents(service: ContextService) -> None:
    assert service.list("alpha") == []
    for patch in (ContextUpdate(), ContextUpdate(body="New")):
        with pytest.raises(MissingDocumentError):
            service.update("alpha", "missing", patch)
    with pytest.raises(MissingDocumentError):
        service.get("alpha", "missing")


def test_every_operation_requires_plan(service: ContextService, metadata: ContextMetadata) -> None:
    service.document_store.create(
        service.layout.context("missing", "orphan"), Document(metadata=metadata, body="Body")
    )
    for operation in (
        lambda: service.create("missing", "new", metadata),
        lambda: service.get("missing", "orphan"),
        lambda: service.update("missing", "orphan", ContextUpdate(body="Changed")),
        lambda: service.update("missing", "orphan", ContextUpdate()),
        lambda: service.list("missing"),
    ):
        with pytest.raises(MissingDocumentError) as error:
            operation()
        assert error.value.path == service.layout.plan("missing")
    assert not (service.document_store.root / service.layout.context("missing", "new")).exists()
    assert (
        service.document_store.read(
            service.layout.context("missing", "orphan"), ContextMetadata
        ).body
        == "Body"
    )


@pytest.mark.parametrize(
    "name",
    ["", "/abs", "../x", "a/../x", "a/./x", "a//x", "a/", "a/ x", "a/x ", "C:/x", "a\\x", "a/\nx"],
)
def test_invalid_names(service: ContextService, metadata: ContextMetadata, name: str) -> None:
    for operation in (
        lambda: service.layout.context("alpha", name),
        lambda: service.create("alpha", name, metadata),
        lambda: service.get("alpha", name),
        lambda: service.update("alpha", name, ContextUpdate()),
    ):
        with pytest.raises(ValidationError):
            operation()


@pytest.mark.parametrize(
    "patch",
    [{"status": "done"}, {"body": None}, {"created": "2026-01-01T00:00:00Z"}, {"unknown": 1}],
)
def test_patch_validation(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ContextUpdate.model_validate(patch)


def test_method_validation(service: ContextService, metadata: ContextMetadata) -> None:
    for operation in (
        lambda: service.create("../bad", "research", metadata),
        lambda: service.get("../bad", "research"),
        lambda: service.update("../bad", "research", ContextUpdate()),
        lambda: service.list("../bad"),
    ):
        with pytest.raises(ValidationError):
            operation()
    with pytest.raises(ValidationError):
        service.create("alpha", "research", {"summary": "missing date"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.create("alpha", "research", {"created": "2026-09-22T12:00:00"})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.create("alpha", "research", metadata, None)  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.update("alpha", "research", {"body": None})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.list("alpha", {"limit": 0})  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValidationError):
        service.list("alpha", {"statuses": ["done"]})  # pyright: ignore[reportArgumentType]


def test_nested_round_trip_and_query(service: ContextService, metadata: ContextMetadata) -> None:
    for name in ("nested/research", "other/research", "research.v2"):
        service.create("alpha", name, metadata)
    for summary in service.list("alpha"):
        context = service.get("alpha", summary.name)
        assert context.path == summary.path
        assert context.modified_at == summary.last_activity_at
        assert "body" not in summary.model_dump()
        assert ContextSummary.model_validate(json.loads(summary.model_dump_json())) == summary
        updated = service.update("alpha", summary.name, ContextUpdate(body=summary.name))
        assert updated.document.body == summary.name
    service.update("alpha", "nested/research", ContextUpdate(body="OAuth"))
    found = service.list("alpha", DocumentQuery(search="oauth", search_body=True))
    assert [context.name for context in found] == ["nested/research"]


def test_explicit_plan_isolation(
    service: ContextService, metadata: ContextMetadata, tmp_path: Path
) -> None:
    state = ProjectStateStore(UPath(tmp_path / "state.toml"))
    state.write(ProjectState(project_name="demo"))
    plans = PlanService(service.document_store, service.layout, state)
    plans.create("beta", PlanMetadata(created=datetime(2026, 9, 22, tzinfo=UTC)))
    plans.set_current("alpha")
    service.create("beta", "research", metadata, "Beta")
    plans.set_current("beta")
    service.create("alpha", "research", metadata, "Alpha")
    service.update("alpha", "research", ContextUpdate(body="Alpha only"))
    assert service.get("beta", "research").document.body == "Beta"
    assert service.get("alpha", "research").document.body == "Alpha only"
    assert service.list("beta")[0].metadata.model_dump(exclude={"summary"}) == metadata.model_dump(
        exclude={"summary"}
    )
    assert service.list("alpha")[0].summary == "Alpha only"
    assert state.read().current_plan == "beta"


def test_delegation(
    service: ContextService, metadata: ContextMetadata, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.create("alpha", "zulu", metadata)
    service.create("alpha", "alpha", metadata)
    records = service.document_store.list(
        service.layout.context_collection("alpha"), ContextMetadata, DocumentQuery(descending=True)
    )
    listing = Mock(return_value=records)
    monkeypatch.setattr(service.document_store, "list", listing)
    query = DocumentQuery(search="no match", limit=1)
    assert [item.name for item in service.list("alpha", query)] == ["zulu", "alpha"]
    listing.assert_called_once_with(
        service.layout.context_collection("alpha"), ContextMetadata, query
    )


class AlternateLayout(Layout):
    @override
    def plan(self, name: str) -> PurePosixPath:
        return PurePosixPath("registry", NameInput(name=name).name, "index.md")

    @override
    def context(self, plan: str, name: str) -> PurePosixPath:
        return PurePosixPath(
            "registry",
            NameInput(name=plan).name,
            "notes",
            f"{ContextNameInput(name=name).name}.note",
        )

    @override
    def context_collection(self, plan: str) -> DocumentCollection:
        return DocumentCollection(
            path=PurePosixPath("registry", NameInput(name=plan).name, "notes"),
            pattern=PurePosixPath("**/*.note"),
        )


def test_layout_controls_lookup_and_discovery(
    service: ContextService, metadata: ContextMetadata
) -> None:
    layout = AlternateLayout()
    service.document_store.create(
        layout.plan("alpha"),
        Document(metadata=PlanMetadata(created=metadata.created), body=""),
    )
    alternate = ContextService(service.document_store, layout)
    service.create("alpha", "ignored", metadata)
    context = alternate.create("alpha", "nested/research", metadata, "Body")
    assert context.path == PurePosixPath("registry/alpha/notes/nested/research.note")
    assert [summary.name for summary in alternate.list("alpha")] == ["nested/research"]
    assert alternate.get("alpha", "nested/research") == context
    assert (
        alternate.update("alpha", "nested/research", ContextUpdate(body="Changed")).document.body
        == "Changed"
    )
